"""Validate the administrator's local entry before applying Zhipu configuration."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from datetime import datetime, timezone

import httpx


ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "infra/runtime/zhipu-api.local.txt"
CHAT = ROOT / "products/librechat-custom"
BASE_URL = "https://open.bigmodel.cn/api/paas/v4/"


class ConfigurationError(ValueError):
    pass


def load_entry(path=ENTRY):
    values = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or key.strip() in values:
            raise ConfigurationError("INVALID_ENTRY")
        values[key.strip()] = value.strip()
    if set(values) != {"ZHIPU_API_KEY", "ZHIPU_MODEL", "ZHIPU_BASE_URL"}:
        raise ConfigurationError("INVALID_ENTRY_FIELDS")
    if not re.fullmatch(r"[A-Za-z0-9._-]{10,500}", values["ZHIPU_API_KEY"]):
        raise ConfigurationError("INVALID_OR_EMPTY_API_KEY")
    if not re.fullmatch(r"glm-[A-Za-z0-9._-]{1,80}", values["ZHIPU_MODEL"]):
        raise ConfigurationError("INVALID_MODEL")
    if values["ZHIPU_BASE_URL"].rstrip("/") != BASE_URL.rstrip("/"):
        raise ConfigurationError("STANDARD_ZHIPU_ENDPOINT_REQUIRED")
    values["ZHIPU_BASE_URL"] = BASE_URL
    return values


def validate(values):
    body = {
        "model": values["ZHIPU_MODEL"], "temperature": 0, "max_tokens": 256,
        "thinking": {"type": "disabled"},
        "messages": [{"role": "user", "content":
                      'Synthetic connectivity check. Return JSON only: {"ok":true}'}],
        "response_format": {"type": "json_object"},
    }
    checks = {}
    with httpx.Client(timeout=45, trust_env=False, headers={
        "Authorization": "Bearer " + values["ZHIPU_API_KEY"],
    }) as client:
        response = client.post(BASE_URL + "chat/completions", json=body)
        if response.status_code != 200:
            raise ConfigurationError(f"ZHIPU_HTTP_{response.status_code}")
        try:
            result = json.loads(response.json()["choices"][0]["message"]["content"])
        except (ValueError, KeyError, TypeError, IndexError) as exc:
            raise ConfigurationError("ZHIPU_INVALID_JSON_OUTPUT") from exc
        if result != {"ok": True}:
            raise ConfigurationError("ZHIPU_INVALID_JSON_OUTPUT")
        checks["json_object"] = "PASS"
        body.pop("response_format")
        body.update(stream=True, messages=[{"role": "user", "content":
                    "Synthetic streaming check. Reply with the single word READY."}])
        parts, done = [], False
        with client.stream("POST", BASE_URL + "chat/completions", json=body) as stream:
            if stream.status_code != 200:
                raise ConfigurationError(f"ZHIPU_STREAM_HTTP_{stream.status_code}")
            for line in stream.iter_lines():
                if line == "data: [DONE]":
                    done = True
                elif line.startswith("data: "):
                    try:
                        choices = json.loads(line[6:]).get("choices", [])
                        if choices:
                            parts.append(choices[0].get("delta", {}).get("content") or "")
                    except (ValueError, TypeError, KeyError, AttributeError) as exc:
                        raise ConfigurationError("ZHIPU_INVALID_STREAM") from exc
        if not done or "READY" not in "".join(parts):
            raise ConfigurationError("ZHIPU_INCOMPLETE_STREAM")
        checks["stream"] = "PASS"
    return checks


def update_env(text, changes):
    lines = []
    remaining = dict(changes)
    for line in text.splitlines():
        key = line.partition("=")[0]
        if key in changes:
            if key in remaining:
                lines.append(f"{key}={remaining.pop(key)}")
        else:
            lines.append(line)
    lines.extend(f"{key}={value}" for key, value in remaining.items())
    return "\n".join(lines) + "\n"


def render_config(text, model):
    # Use LibreChat's existing YAML parser and endpoint options; never embed the key.
    source = r"""
const yaml = require('js-yaml');
const fs = require('node:fs');
const { configSchema } = require('./packages/data-provider/dist');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const config = yaml.load(input.text);
const existing = config.endpoints.custom.find(e => e.name === 'Zhipu' || e.name === 'DeepSeek');
if (!existing) throw new Error('ENDPOINT_NOT_FOUND');
const endpoint = {
  ...existing, name: 'Zhipu', apiKey: '${ZHIPU_API_KEY}',
  baseURL: 'https://open.bigmodel.cn/api/paas/v4/',
  models: { default: [input.model], fetch: false },
  titleConvo: true, titleModel: input.model, modelDisplayLabel: '智谱',
  addParams: { ...existing.addParams, model: input.model, thinking: { type: 'disabled' } },
};
const other = config.endpoints.custom.filter(e => !['Zhipu', 'DeepSeek'].includes(e.name));
config.endpoints.custom = [
  endpoint,
  { ...endpoint, name: 'DeepSeek', models: { default: [input.model, 'deepseek-flash'], fetch: false } },
  ...other,
];
const spec = config.modelSpecs.list.find(s => s.name === 'life-companion');
if (!spec) throw new Error('MODEL_SPEC_NOT_FOUND');
// Keep the saved spec/endpoint pair valid for existing conversations.
spec.preset = { ...spec.preset, endpoint: 'DeepSeek', model: input.model };
spec.default = false;
spec.showInMenu = false;
const current = config.modelSpecs.list.find(s => s.name === 'life-companion-zhipu');
const next = {
  ...spec, name: 'life-companion-zhipu', default: true, showInMenu: true,
  preset: { ...spec.preset, endpoint: 'Zhipu', model: input.model },
};
if (current) Object.assign(current, next);
else config.modelSpecs.list.push(next);
configSchema.parse(config);
process.stdout.write(yaml.dump(config, { lineWidth: -1, noRefs: true }));
"""
    result = subprocess.run(
        ["node", "-e", source], cwd=CHAT,
        input=json.dumps({"text": text, "model": model}),
        text=True, encoding="utf-8", capture_output=True,
    )
    if result.returncode:
        raise ConfigurationError("LIBRECHAT_CONFIG_VALIDATION_FAILED")
    return result.stdout


def apply(values):
    env_path, yaml_path = CHAT / ".env", CHAT / "librechat.yaml"
    previous = {str(p): p.read_text(encoding="utf-8-sig") for p in (env_path, yaml_path)}
    replacements = {
        env_path: update_env(previous[str(env_path)], {**values, "LIFE_LLM_PROVIDER": "zhipu"}),
        yaml_path: render_config(previous[str(yaml_path)], values["ZHIPU_MODEL"]),
    }
    sys.path.insert(0, str(ROOT / "services/life-core"))
    from app.provisioning import protect
    backup = ROOT / "infra/runtime" / (
        "zhipu-config-before-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".dpapi"
    )
    backup.write_text(protect(previous), encoding="ascii")
    written = []
    try:
        for path, text in replacements.items():
            if path.read_text(encoding="utf-8-sig") != previous[str(path)]:
                raise ConfigurationError("CONFIG_CHANGED_DURING_APPLY")
            temporary = path.with_name(path.name + ".zhipu-pending")
            temporary.write_text(text, encoding="utf-8")
            os.replace(temporary, path)
            written.append(path)
    except Exception:
        for path in written:
            path.write_text(previous[str(path)], encoding="utf-8")
        raise
    return {"encrypted_backup": backup.name, "services_restart_required": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    options = parser.parse_args()
    report = {"started_at": datetime.now(timezone.utc).isoformat(), "status": "FAIL"}
    exit_code = 1
    try:
        values = load_entry()
        report.update(provider="zhipu", model=values["ZHIPU_MODEL"], base_url=BASE_URL)
        report["checks"] = validate(values)
        if options.apply:
            report["configuration"] = apply(values)
        report.update(status="PASS", applied=options.apply)
        exit_code = 0
    except ConfigurationError as exc:
        report["error_code"] = str(exc)
    except httpx.HTTPError:
        report["error_code"] = "ZHIPU_NETWORK_UNAVAILABLE"
    except Exception:
        report["error_code"] = "LOCAL_CONFIGURATION_ERROR"
    report["ended_at"] = datetime.now(timezone.utc).isoformat()
    folder = ROOT / "evidence/v022-zhipu"
    folder.mkdir(exist_ok=True)
    path = folder / ("configure-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".json")
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
