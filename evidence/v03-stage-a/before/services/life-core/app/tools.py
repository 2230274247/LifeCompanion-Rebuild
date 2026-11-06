"""Authenticated read-only tool adapters with durable quotas and source receipts."""
from __future__ import annotations

import hashlib
import html
import ipaddress
import json
import math
import re
from datetime import date, datetime, timedelta, timezone
from typing import Literal
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import httpx
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from .store import utc_now


class Point(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    latitude: float = Field(ge=-90,le=90)
    longitude: float = Field(ge=-180,le=180)


class WeatherInput(Point):
    place_label: str = Field(min_length=1,max_length=80)
    forecast_date: date | None = None
    timezone: str = "UTC"

    @field_validator("timezone")
    @classmethod
    def valid_zone(cls,value):
        try:
            ZoneInfo(value)
        except (KeyError,ValueError) as exc:
            raise ValueError("INVALID_TIMEZONE") from exc
        return value


class RouteInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    origin: Point | None = None
    destination: Point | None = None
    arrival_at: AwareDatetime | None = None


class SearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1,max_length=500)


class PlaceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1,max_length=80)


class ToolRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Literal["weather","route","search","place_search"]
    idempotency_key: str = Field(min_length=8,max_length=160)
    parameters: dict
    source_message_id: str | None = Field(default=None,max_length=200)
    conversation_id: str | None = Field(default=None,max_length=200)


SCHEMAS = {"weather":WeatherInput,"route":RouteInput,"search":SearchInput,"place_search":PlaceInput}
EGRESS = {
    "weather":["explicit latitude/longitude","requested forecast date"],
    "route":["explicit origin/destination coordinates"],
    "search":["explicit public search query"],
    "place_search":["explicit place search query"],
}


def safe_link(value):
    if not isinstance(value,str):
        return False
    parsed = urlparse(value)
    if parsed.scheme not in ("https","http") or not parsed.hostname or parsed.username or parsed.password:
        return False
    if parsed.hostname == "localhost" or parsed.hostname.endswith((".localhost",".local")):
        return False
    try:
        return ipaddress.ip_address(parsed.hostname).is_global
    except ValueError:
        return True


class ToolExecution:
    def __init__(self,store,settings,*,transport=None):
        self.store,self.settings,self.transport = store,settings,transport
        with store.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS tool_executions (
                execution_id TEXT PRIMARY KEY,user_id TEXT NOT NULL,name TEXT NOT NULL,
                request_hash TEXT NOT NULL,source_message_id TEXT,conversation_id TEXT,
                status TEXT NOT NULL,result TEXT NOT NULL DEFAULT '{}',error_code TEXT,
                network_requests INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,expires_at TEXT NOT NULL
            )""")
            db.execute("""UPDATE tool_executions SET status='unknown',
                error_code='TOOL_RESULT_UNKNOWN',updated_at=? WHERE status='running'""",(utc_now(),))

    def catalog(self):
        return [{"name":name,"parameters":schema.model_json_schema(),"read_only":True,
                 "scope":"explicit_public_query","outbound_fields":EGRESS[name],
                 "timeout_seconds":12,"automatic_retries":0}
                for name,schema in SCHEMAS.items()]

    def public(self,row):
        if not row:
            return None
        return {**{key:row[key] for key in (
            "execution_id","name","status","error_code","network_requests","created_at","updated_at")},
            "result":json.loads(row["result"])}

    def cleanup(self):
        with self.store.connect() as db:
            db.execute("""UPDATE tool_executions SET status='expired',result='{}',
                source_message_id=NULL,conversation_id=NULL WHERE expires_at<=? AND status<>'expired'""",
                (utc_now(),))

    def detail(self,owner,identifier):
        self.cleanup()
        with self.store.connect() as db:
            row = db.execute("SELECT * FROM tool_executions WHERE user_id=? AND execution_id=?",
                             (owner,identifier)).fetchone()
        return self.public(row)

    def list(self,owner,conversation_id=None,source_message_id=None):
        self.cleanup()
        with self.store.connect() as db:
            rows = db.execute("""SELECT * FROM tool_executions WHERE user_id=? AND status<>'expired'
                AND (? IS NULL OR conversation_id=?) AND (? IS NULL OR source_message_id=?)
                ORDER BY created_at DESC LIMIT 30""",
                (owner,conversation_id,conversation_id,source_message_id,source_message_id)).fetchall()
        return [self.public(row) for row in rows]

    def delete(self,owner,identifier):
        with self.store.connect() as db:
            return db.execute("""UPDATE tool_executions SET status='deleted',result='{}',
                source_message_id=NULL,conversation_id=NULL,updated_at=?
                WHERE user_id=? AND execution_id=?""",(utc_now(),owner,identifier)).rowcount

    def execute(self,owner,request):
        self.cleanup()
        parameters = SCHEMAS[request.name].model_validate(request.parameters)
        normalized = parameters.model_dump(mode="json")
        # Preserve the initial UTC weather receipts when adding an explicit zone.
        if request.name == "weather" and parameters.timezone == "UTC":
            normalized.pop("timezone")
        canonical = json.dumps({"name":request.name,"parameters":normalized,
            "source":request.source_message_id,"conversation":request.conversation_id},
            sort_keys=True,ensure_ascii=False)
        request_hash = hashlib.sha256(canonical.encode()).hexdigest()
        identifier = "tool_" + hashlib.sha256(f"{owner}:{request.idempotency_key}".encode()).hexdigest()[:28]
        status,error,result = "running",None,{}
        if request.name == "route" and (parameters.origin is None or parameters.destination is None):
            status = "needs_input"
            result = {"missing_field":"origin" if parameters.origin is None else "destination"}
        elif not self.provider_available(request.name):
            status,error = "blocked","TOOL_PROVIDER_UNAVAILABLE"
        if request.name == "weather" and parameters.forecast_date is not None:
            delta = (parameters.forecast_date - datetime.now(ZoneInfo(parameters.timezone)).date()).days
            if not 0 <= delta <= 6:
                raise ValueError("TOOL_FORECAST_DATE_OUTSIDE_HORIZON")
        if request.name == "route" and parameters.arrival_at is not None:
            if parameters.arrival_at <= datetime.now(timezone.utc):
                raise ValueError("TOOL_ARRIVAL_MUST_BE_FUTURE")
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT * FROM tool_executions WHERE execution_id=? AND user_id=?",
                                  (identifier,owner)).fetchone()
            if existing:
                if existing["request_hash"] != request_hash:
                    raise ValueError("TOOL_IDEMPOTENCY_CONFLICT")
                return self.public(existing)
            if status == "running" and db.execute(
                    "SELECT COALESCE(sum(network_requests),0) FROM tool_executions").fetchone()[0] >= self.settings.tool_request_budget:
                status,error = "blocked","TOOL_REQUEST_BUDGET"
            stamp = utc_now()
            db.execute("""INSERT INTO tool_executions
                (execution_id,user_id,name,request_hash,source_message_id,conversation_id,
                 status,result,error_code,network_requests,created_at,updated_at,expires_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (identifier,owner,request.name,request_hash,request.source_message_id,request.conversation_id,
                 status,json.dumps(result),error,int(status=="running"),stamp,stamp,
                 (datetime.now(timezone.utc)+timedelta(days=1)).isoformat()))
        if status == "running":
            try:
                result = self.dispatch(request.name,parameters)
                status = "succeeded"
            except httpx.HTTPStatusError as exc:
                status,error = "failed",f"TOOL_HTTP_{exc.response.status_code}"
            except httpx.HTTPError:
                status,error = "unknown","TOOL_RESULT_UNKNOWN"
            except (ValueError,KeyError,IndexError,TypeError,AttributeError):
                status,error = "failed","TOOL_INVALID_OUTPUT"
            with self.store.connect() as db:
                # A deletion while HTTP was in flight must never restore content.
                db.execute("""UPDATE tool_executions SET status=?,result=?,error_code=?,updated_at=?
                    WHERE execution_id=? AND user_id=? AND status='running'""",
                    (status,json.dumps(result),error,utc_now(),identifier,owner))
        return self.detail(owner,identifier)

    def provider_available(self,name):
        if name in ("weather","place_search"):
            return self.settings.tool_weather_provider == "open_meteo"
        if name == "route":
            return self.settings.tool_route_provider == "osrm_demo"
        parsed = urlparse(self.settings.tool_search_url)
        return (parsed.scheme=="http" and parsed.hostname=="127.0.0.1" and not parsed.username
                and not parsed.password and not parsed.query and not parsed.fragment)

    def get(self,url,parameters):
        with httpx.Client(timeout=httpx.Timeout(12,connect=4),trust_env=False,follow_redirects=False,
                          transport=self.transport) as client:
            with client.stream("GET",url,params=parameters,headers={
                    "User-Agent":"LifeCompanion-Rebuild/0.1 (isolated research acceptance)"}) as response:
                response.raise_for_status()
                chunks,total = [],0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > 262144:
                        raise ValueError("TOOL_RESPONSE_TOO_LARGE")
                    chunks.append(chunk)
                return json.loads(b"".join(chunks)),str(response.request.url)

    def dispatch(self,name,parameters):
        stamp = utc_now()
        if name == "place_search":
            body,url = self.get("https://geocoding-api.open-meteo.com/v1/search",
                               {"name":parameters.query,"count":5,"language":"zh","format":"json"})
            places = []
            for item in body.get("results",[])[:5]:
                point = Point.model_validate({key:item[key] for key in ("latitude","longitude")})
                places.append({**point.model_dump(),"name":str(item["name"])[:80],
                    "country":str(item.get("country",""))[:80],"admin1":str(item.get("admin1",""))[:80]})
            return {"places":places,"requires_user_selection":True,
                    "sources":[{"title":"Open-Meteo place search","url":url,"fetched_at":stamp}]}
        if name == "weather":
            params = {"latitude":parameters.latitude,"longitude":parameters.longitude,"timezone":parameters.timezone}
            if parameters.forecast_date is None:
                params["current"] = "temperature_2m,precipitation"
            else:
                params.update(daily="temperature_2m_max,temperature_2m_min,precipitation_sum",
                              start_date=parameters.forecast_date.isoformat(),end_date=parameters.forecast_date.isoformat())
            body,url = self.get("https://api.open-meteo.com/v1/forecast",params)
            if parameters.forecast_date is None:
                current = body["current"]
                observed = datetime.fromisoformat(current["time"])
                if observed.tzinfo is None:
                    observed = observed.replace(tzinfo=ZoneInfo(parameters.timezone))
                if abs((datetime.now(timezone.utc)-observed).total_seconds()) > 7200:
                    raise ValueError("STALE_WEATHER")
                if not all(type(current[key]) in (int,float) and math.isfinite(current[key])
                           for key in ("temperature_2m","precipitation")):
                    raise ValueError("INVALID_WEATHER")
                data = {"current":current,"units":body["current_units"]}
            else:
                if body["daily"]["time"] != [parameters.forecast_date.isoformat()]:
                    raise ValueError("WRONG_FORECAST_DAY")
                data = {"daily":body["daily"],"units":body["daily_units"]}
            return {"place_label":parameters.place_label,"requested_coordinates":parameters.model_dump(
                include={"latitude","longitude"}),"timezone":parameters.timezone,"kind":"modeled_weather_estimate",
                **data,"sources":[{"title":"Open-Meteo forecast","url":url,"fetched_at":stamp}]}
        if name == "route":
            origin,destination = parameters.origin,parameters.destination
            coordinates = f"{origin.longitude},{origin.latitude};{destination.longitude},{destination.latitude}"
            body,url = self.get("https://router.project-osrm.org/route/v1/driving/"+coordinates,
                               {"overview":"false"})
            if body["code"] != "Ok":
                raise ValueError("ROUTE_UNAVAILABLE")
            route = body["routes"][0]
            duration,distance = route["duration"],route["distance"]
            if (type(duration) not in (int,float) or type(distance) not in (int,float)
                    or not math.isfinite(duration) or not math.isfinite(distance)
                    or duration <= 0 or distance <= 0):
                raise ValueError("INVALID_ROUTE")
            result = {"duration_seconds":duration,"distance_meters":distance,
                "kind":"static_driving_estimate_no_live_traffic","planning_buffer_minutes":15,
                "sources":[{"title":"OSRM route estimate","url":url,"fetched_at":stamp}]}
            if parameters.arrival_at:
                result["suggested_departure_at"] = (
                    parameters.arrival_at-timedelta(seconds=duration,minutes=15)).isoformat()
            return result
        body,_ = self.get(self.settings.tool_search_url.rstrip("/")+"/search",
                           {"q":parameters.query,"format":"json"})
        results = []
        for item in body.get("results",[])[:10]:
            if not safe_link(item.get("url")):
                continue
            results.append({"title":html.unescape(re.sub("<[^>]+>","",str(item.get("title",""))))[:200],
                "url":item["url"],"summary":html.unescape(re.sub("<[^>]+>","",str(item.get("content",""))))[:600],
                "fetched_at":stamp})
            if len(results) == 5:
                break
        return {"results":results,"retrieved_at":stamp,
                "no_results":not bool(results)}
