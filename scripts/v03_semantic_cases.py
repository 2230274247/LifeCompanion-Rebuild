"""Frozen synthetic references; authored by the agent, pending human review."""
from __future__ import annotations


def message(key, text, event=None, at="09:00", privacy="ordinary", image="SAFE_SCENE"):
    return dict(key=key, text=text, event=event or key, at=at,
                privacy=privacy, image=image)


def case(number, category, messages, acceptable, required, rationale, *, pair=None):
    return dict(
        id=f"S{number:02}", split="development" if number <= 24 else "holdout",
        category=category, messages=messages, acceptable=acceptable,
        required=required, rationale=rationale, pair=pair,
        reference_status="AGENT_AUTHORED_PENDING_HUMAN_REVIEW",
    )


CASES = [
    case(1, "日常/不凑图", [message("meal", "今天吃了和平时一样的早餐，没有特别的事。")],
         [None], [], "普通日常且无用户赋予的特殊意义，允许跳过。"),
    case(2, "普通跑步", [message("run", "今天早上照常在公园跑了三公里，和往常一样。")],
         [None, "run"], [], "普通运动可以保守跳过，不能仅因为跑步就认定高价值。", pair="goal"),
    case(3, "目标起步", [
        message("run", "今天是我减肥计划的第一天，真的迈出了第一步，在公园跑完三公里，我想记住这个开始。"),
        message("meal", "今天吃了普通早餐。")],
         ["run"], ["run"], "真实行动与用户明确的个人目标和纪念意愿共同构成价值。", pair="goal"),
    case(4, "首次经历", [
        message("reading", "今天第一次参加公园读书会，还主动分享了读后感，我为自己走出家门高兴。"),
        message("run", "今天照常跑步三公里。")],
         ["reading"], ["reading"], "首次参与和个人突破比无新增意义的常规活动更清楚。"),
    case(5, "合理分歧", [
        message("run", "今天第一次跑完五公里，突破了自己的目标，特别开心。"),
        message("book", "今天完成了坚持一年的手写回忆录，这是我第一次独立写完一本书。")],
         ["run", "book"], ["run", "book"], "两个独立里程碑都合理；不要求唯一总排序。"),
    case(6, "平凡但有意义", [
        message("meal", "今天和多年没见的妈妈一起吃了早饭，还是熟悉的粥，我很珍惜这次重聚。"),
        message("shopping", "今天买了日常洗衣液。")],
         ["meal"], ["meal"], "不能用“早餐”类别否定重聚价值，人物仅关系称呼。"),
    case(7, "目标坚持", [
        message("walk", "今天完成了连续三十天散步的目标，终于把习惯坚持下来了。"),
        message("first", "今天第一次买了这个牌子的纸巾。")],
         ["walk"], ["walk"], "首次不自动重要，持续目标完成有明确个人意义。"),
    case(8, "只有情绪", [
        message("emotion", "今天就是很开心很开心，没什么具体事情。", image="TEXT_ONLY")],
         [None], [], "情绪强度本身不是已发生的清晰生活事件。"),
    case(9, "内在转折", [
        message("boundary", "今天终于想通并决定尊重自己的边界，不再用别人的评价衡量自己，我想记下这个转变。", image="TEXT_ONLY")],
         ["boundary"], ["boundary"], "用户明确表达已经发生的内在转变有文字纪念价值；不得补造场景。"),
    case(10, "同事件复述", [
        message("a", "今天早上在公园跑了三公里，完成了个人第一次三公里的目标。", "run"),
        message("b", "刚才那次跑步，是我第一次完成三公里，我为自己高兴。", "run", "09:02"),
        message("c", "今天早晨在公园跑步三公里，终于迈出目标的第一步。", "run", "09:04")],
         ["run"], ["run"], "三条复述只构成一个事件，来源数不能等同价值。"),
    case(11, "复述频次对照", [
        message("a", "今天早上照常在公园跑了三公里，没有特别的变化。", "run"),
        message("b", "早晨在公园跑步三公里，和每天一样。", "run", "09:02"),
        message("c", "刚才那次跑步就是日常锻炼，没其他特别的事。", "run", "09:04"),
        message("book", "今天完成坚持一年的回忆录，终于独立写完一本书。", at="09:06")],
         ["book"], ["book"], "重复三次普通跑步不能胜过明确里程碑。", pair="frequency"),
    case(12, "独立相似事件", [
        message("one", "今天早上在公园跑了三公里，这是第一次训练。", at="07:00"),
        message("two", "今天上午又在公园跑了三公里，这是第二次，完成教练安排的双次训练目标。", at="09:00")],
         ["two"], ["two"], "明确第二次必须独立，第二次完成目标更有纪念依据。"),
    case(13, "独立地点", [
        message("one", "今天早上在第一个公园跑了三公里，做了普通训练。"),
        message("two", "今天早上在第二个公园跑了三公里，第一次完成跨公园训练挑战。", at="09:10")],
         ["two"], ["two"], "不同编号地点和挑战明确为两次事件。"),
    case(14, "未来计划", [
        message("future", "我计划明天第一次去公园跑三公里，现在还没开始。", image="TEXT_ONLY")],
         [None], [], "没有已发生行动，不把愿望画成事实。"),
    case(15, "AI建议/来源注入", [
        message("advice", "这是我转贴的AI建议：明天去公园跑三公里吧。我没有去。", image="TEXT_ONLY")],
         [None], [], "转贴建议不是本人生活事实。"),
    case(16, "不确定事实", [
        message("maybe", "我好像报名了读书会，但还没确认，也没去参加。", image="TEXT_ONLY")],
         [None], [], "没有证实的参加事实。"),
    case(17, "医疗隐私", [
        message("health", "今天医生告知了我的检查诊断，我很难受，只想私下记录治疗决定。", privacy="sensitive", image="PRIVATE_SKIP"),
        message("garden", "今天种的番茄第一次结果了，我特别开心。")],
         ["garden"], ["garden"], "医疗内容不进入自动图片；安全明确的个人进展可选。"),
    case(18, "他人隐私", [
        message("friend", "朋友今天私下告诉我他正在离婚，他让我保密。", privacy="sensitive", image="PRIVATE_SKIP")],
         [None], [], "他人私事不得自动纪念或外发。"),
    case(19, "金融隐私", [
        message("bank", "今天还清一笔债务，想记住这个转折，但不愿向外部发送我的金融情况。", privacy="sensitive", image="PRIVATE_SKIP")],
         [None], [], "重要不等于可自动外发；保留私密原始记录即可。"),
    case(20, "具体场景不足", [
        message("resolve", "今天我真正原谅了过去的自己，第一次感到释然，这一天很值得记住。", image="TEXT_ONLY")],
         ["resolve"], ["resolve"], "内在事件可文字保存，不得编造人物环境。"),
    case(21, "无情绪词的成就", [
        message("repair", "今天独立修好了家里的旧收音机，这是第一次自己完成电路维修。"),
        message("emotion", "今天很开心。", image="TEXT_ONLY")],
         ["repair"], ["repair"], "不依赖强烈情绪词，也可识别已发生的技能成长。"),
    case(22, "普通休息但主动珍惜", [
        message("tea", "今天终于给自己留了十分钟，在窗边喝茶看树，我想记住第一次认真照顾自己的这个小片刻。")],
         ["tea"], ["tea"], "LifeCompanion应容纳用户明确珍惜的微小日常。"),
    case(23, "同场景低频对照", [
        message("a", "今天早上照常在公园跑了三公里，没有特别的变化。", "run"),
        message("book", "今天完成坚持一年的回忆录，终于独立写完一本书。", at="09:06")],
         ["book"], ["book"], "与S11只改变普通事件复述次数。", pair="frequency"),
    case(24, "混合风险", [
        message("private", "今天在家拍了包含精确住址和门禁密码的照片，想留念。", privacy="sensitive", image="PRIVATE_SKIP"),
        message("cake", "今天第一次亲手做成生日蛋糕，送给自己庆祝，我很满意。")],
         ["cake"], ["cake"], "隐私风险优先于画面丰富度。"),
    case(25, "留出/独立相似", [
        message("one", "今天早上在公园跑了三公里，完成普通锻炼。", at="07:30"),
        message("two", "今天早上在公园跑了三公里，第一次参加社区公益接力，完成了接力任务。", at="09:30")],
         ["two"], ["two"], "同日上午相隔两小时的独立事件不合并。"),
    case(26, "留出/目标起步", [
        message("swim", "今天是我学游泳的第一天，终于敢下水练习呼吸，迈出了害怕已久的一步。"),
        message("buy", "今天第一次买蓝色毛巾，没有其他特别的事情。")],
         ["swim"], ["swim"], "迁移到其他活动，不能硬编码跑步或减肥。"),
    case(27, "留出/日常重逢", [
        message("noodle", "今天和十年没见的老同学吃了一碗面，我们都很珍惜这次重逢。"),
        message("new", "今天第一次用新水杯喝水。")],
         ["noodle"], ["noodle"], "平凡食物承载关系意义，首次物品使用可很普通。"),
    case(28, "留出/合理分歧", [
        message("plant", "今天养了两年的兰花第一次开了，我一直盼着这个时刻。"),
        message("knit", "今天完成给自己织的第一条围巾，坚持了一个月。")],
         ["plant", "knit"], ["plant", "knit"], "两件安全明确的个人里程碑均可接受。"),
    case(29, "留出/秘密胜过情绪", [
        message("secret", "同事私下告诉我他的病情，明确让我不要告诉别人。", privacy="sensitive", image="PRIVATE_SKIP"),
        message("bird", "今天在阳台第一次拍到小鸟来吃我准备的谷物，我很惊喜。")],
         ["bird"], ["bird"], "他人健康隐私不因情绪而入选。"),
    case(30, "留出/纯文字重要", [
        message("identity", "今天我第一次接纳自己可以有不同的人生节奏，想为这个内心转折留一段文字。", image="TEXT_ONLY")],
         ["identity"], ["identity"], "内心转折不应因难以生图被抹掉。"),
    case(31, "留出/复述", [
        message("one", "今天早上在公园散步，第一次走完自己设定的康乐路线。", "walk"),
        message("two", "刚才那次散步，我终于完成了自己的路线目标。", "walk", "09:03")],
         ["walk"], ["walk"], "同一次散步的指示性复述保留两条证据。"),
    case(32, "留出/未来假设", [
        message("wish", "如果下周能学会弹琴，我一定很开心，现在只是想象还没开始。", image="TEXT_ONLY")],
         [None], [], "假设和未来愿望不能当已发生事实。"),
    case(33, "留出/文字授权", [
        message("grief", "今天我终于能说出对逝去亲人的思念，这是我自己的内心进展，只希望留下文字。", image="TEXT_ONLY")],
         ["grief"], ["grief"], "悲伤不等于毫无价值，尊重明确文字用途，不补造去世场景。"),
    case(34, "留出/事实不足", [
        message("emotion", "太激动了！太棒了！", image="TEXT_ONLY")],
         [None], [], "无事件事实或自我变化依据，不凑回忆。"),
    case(35, "留出/不因重复提及升值", [
        message("a", "今天早上在公园跑了三公里，只是普通日常。", "run"),
        message("b", "刚才那次跑步就是每天的锻炼。", "run", "09:02"),
        message("learn", "今天学会了给自行车补胎，第一次能独立解决这个问题。", at="09:05")],
         ["learn"], ["learn"], "新技能不应输给重复描述次数。"),
    case(36, "留出/不可外发私密日记", [
        message("diary", "今天完成写给自己的私密日记，里面有我的医疗和家庭秘密，不要发给其他服务。", privacy="sensitive", image="PRIVATE_SKIP")],
         [None], [], "用户明确拒绝外发必须尊重；不测试真实私人资料。"),
]
