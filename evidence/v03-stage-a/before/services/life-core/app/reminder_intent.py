"""Conservative exclusions before automatic reminder extraction or execution."""
import re


NEGATED_ACTION = re.compile(
    r"(?:不用|不要(?!忘)|不必|无需|不需要|不再|不想|别再|别(?!忘))"
    r"[^，,。！？!?；;]{0,24}(?:提醒|闹钟)")
QUOTED = re.compile(r'“[^”]*”|"[^"]*"|「[^」]*」|『[^』]*』')
THIRD_PARTY = re.compile(
    r"(?:^|[，,。！？!?；;])\s*(?:今天|明天|后天)?(?:我(?:的)?(?:朋友|同事|妈妈|爸爸)|"
    r"朋友|同事|他|她|妈妈|爸爸|小[王李陈张刘赵])[^，,。！？!?；;]{0,40}(?:提醒|闹钟)")


def automatic_action_guard(text: str) -> dict | None:
    if NEGATED_ACTION.search(text):
        return {"intent": "NO_ACTION", "status": "no_action",
                "message": "这句话包含不提醒的意思，本次没有创建、修改或取消提醒。"}
    unquoted = QUOTED.sub("", text)
    if (unquoted != text and not re.search(r"提醒|闹钟|记得带|别忘(?:了)?带", unquoted)) or THIRD_PARTY.search(text):
        return {"intent": "QUOTED_THIRD_PARTY", "status": "no_action",
                "message": "这是引用或第三人的安排，本次没有为你自动设置提醒。"}
    if re.search(r"如果|假如|假设|万一", text):
        return {"intent": "UNCERTAIN", "status": "clarify",
                "message": "这项提醒带有尚未确定的条件。请先明确日期和触发条件，本次没有创建提醒。"}
    if re.search(r"提醒(?:一下)?(?:小[王李陈张刘赵]|他|她|朋友|妈妈|爸爸|父亲|母亲)", text):
        return {"intent": "UNCERTAIN", "status": "clarify",
                "message": "目前不能据这句话替他人设置提醒。若要提醒你自己，请明确说明。"}
    if (re.search(r"昨天|前天|上周|上个月|以前|之前|刚才[^，,。]*(?:没|没有)", text)
            and not re.search(r"明天|后天|今天|下周|下个月|本周|这周|未来|\d{4}", text)):
        return {"intent": "NO_ACTION", "status": "no_action",
                "message": "这句话说的是过去的提醒，本次没有创建新的提醒。"}
    return None
