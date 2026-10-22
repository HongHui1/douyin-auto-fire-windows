"""Offline, reviewed friend-only copy. No API, prompt, recipient interpolation or disk writes."""
from __future__ import annotations

import hashlib
import random
import unicodedata
from datetime import date, datetime
from zoneinfo import ZoneInfo


# Review the meaning of every new entry. Filtering is only a second line of defence,
# not permission to accept arbitrary generated text. Literary entries quote named
# authors only: no original poetry, imitations or generated translations.
# Foreign poems retain their source language; sonnet excerpts are labelled.
# Sources and excerpt boundaries: docs/literary-sources.md.
BANK: dict[str, tuple[str, ...]] = {
    "literary": (
        "【古诗·节选】\n明月松间照，清泉石上流。\n——王维《山居秋暝》",
        "【登高一页】\n白日依山尽，黄河入海流。\n欲穷千里目，更上一层楼。\n——王之涣《登鹳雀楼》",
        "【古诗·节选】\n等闲识得东风面，万紫千红总是春。\n——朱熹《春日》",
        "【古诗·节选】\n问渠那得清如许？为有源头活水来。\n——朱熹《观书有感·其一》",
        "【古诗·节选】\n横看成岭侧成峰，远近高低各不同。\n——苏轼《题西林壁》",
        "【古诗·节选】\n飞流直下三千尺，疑是银河落九天。\n——李白《望庐山瀑布》",
        "【古诗】\n独坐幽篁里，弹琴复长啸。\n深林人不知，明月来相照。\n——王维《竹里馆》",
        "【古诗】\n两个黄鹂鸣翠柳，一行白鹭上青天。\n窗含西岭千秋雪，门泊东吴万里船。\n——杜甫《绝句》",
        "【古诗·节选】\n接天莲叶无穷碧，映日荷花别样红。\n——杨万里《晓出净慈寺送林子方》",
        "【古诗·节选】\n采菊东篱下，悠然见南山。\n——陶渊明《饮酒·其五》",
        "【古诗】\n自古逢秋悲寂寥，我言秋日胜春朝。\n晴空一鹤排云上，便引诗情到碧霄。\n——刘禹锡《秋词·其一》",
        "【古诗·节选】\n山重水复疑无路，柳暗花明又一村。\n——陆游《游山西村》",
        "【俳句·日文原文】\n古池や蛙飛びこむ水の音\n——松尾芭蕉（以首句识别）",
        "【俳句·日文原文】\n閑さや岩にしみ入る蝉の声\n——松尾芭蕉《奥の細道》山寺一节",
        "【十四行诗·英文原文节选】\nThe poetry of earth is never dead:\nWhen all the birds are faint with the hot sun,\nAnd hide in cooling trees, a voice will run\nFrom hedge to hedge about the new-mown mead;\n——济慈《On the Grasshopper and Cricket》第1—4行",
        "【十四行诗·英文原文节选】\nThe beauty of the morning; silent, bare,\nShips, towers, domes, theatres, and temples lie\nOpen unto the fields, and to the sky;\nAll bright and glittering in the smokeless air.\n——华兹华斯《Composed upon Westminster Bridge, Sept. 3, 1802》第5—8行",
    ),
    "daily": (
        "🔥 今日续火已打卡。生活可以慢半拍，饭点尽量别迟到。",
        "今日状态：脑子正在加载，饭量已经就绪。🔥",
        "给生活加一点燃料，给待办减一点难度。今日份柴火送到。🔥",
        "今天的运动计划：在理想和沙发之间反复横跳。🔥",
        "报告：精神状态良好，只是偶尔想变成路边晒太阳的猫。🔥",
        "今日小目标：把水喝够，把饭吃香，把复杂问题留给清醒的脑袋。🔥",
        "本条消息含有零卡路里柴火，可放心接收。🔥",
        "人生进度条加载中。先存个档，再去研究下一顿吃啥。🔥",
        "我的待办清单很有礼貌：每天都留着，等我明天再做。🔥",
        "今日冷知识：把烦恼写在纸上，再翻过来，就暂时看不见了。🔥",
        "续火小队路过：添柴一根，顺便检查零食库存。🔥",
        "今日宜：吃好喝好。今日忌：拿计算器算自己浪费了多少时间。🔥",
        "已给今天加了一个书签：普通的一天，也值得认真吃饭。🔥",
        "本来想一鸣惊人，结果午睡醒来一鸣惊闹钟。🔥",
        "今日能量来源：碳水、阳光，以及终于找到的充电线。🔥",
        "收到生活的新关卡。先看攻略，再决定要不要先吃点东西。🔥",
        "天气随机，饭要按时。今日份小火苗已配送。🔥",
        "今天也当个实干派：先把“该休息了”这件事落实。🔥",
        "大脑：我要高效运行。身体：先批准五分钟发呆。🔥",
        "今日互联网巡逻完毕，发现大家都很会整活。顺手添柴。🔥",
    ),
    "roleplay": (
        "【AI 值班员】扫描完成：今日份柴火已入库。建议执行喝水指令。🔥",
        "【AI 日志】复杂问题等待计算，午饭问题优先处理。续火模块待命中。🔥",
        "【AI 小助手】已将“发呆五分钟”加入合理休息列表。今日补给：柴火一份。🔥",
        "【皇帝诏曰】传朕口谕：今日灶房加柴，诸位按时用膳，奏折饭后再议。🔥",
        "【皇帝诏曰】今日早朝议题：午饭吃什么。众卿尚未统一意见，先给炉子添柴。🔥",
        "【魔王日常】本王宣布：今日不征服世界，先把城堡厨房的火续上。🔥",
        "【魔王日常】勇者请稍等，最终关卡正在拖地。旁边有柴，自取一根。🔥",
        "【NPC 提示】日常任务已刷新：喝水、吃饭、休息。路过营地，添一根柴。🔥",
        "【NPC 对话】这位冒险者，前方没有隐藏收费项目，只有一堆待整理的背包。🔥",
        "【太空船长】航行日志：燃料补给到位，今日目标是平稳抵达晚饭时间。🔥",
        "【山神值班】今日山中无大事，松鼠盘点松果，本神负责添柴。🔥",
        "【游戏铁匠】叮！炉温正常。今日可锻造物品：一把解决小麻烦的扳手。🔥",
        "【机器人播报】正在升级休息程序……请勿拔掉零食供应。附送柴火一根。🔥",
        "【江湖掌柜】客官，今日菜单：清茶一壶，闲事少管，炉火照常。🔥",
        "【探险队后勤】指南针已检查，水壶已装满。先在营地补点燃料。🔥",
        "【魔法学徒】施法成功：把一根木柴变成了两截。总质量保持不变。🔥",
    ),
    "event": (
        "【虚构事件·系统故障】火苗被误识别成烤红薯，现已人工纠正。附赠想象中的红薯一个。🔥",
        "【虚构事件·火种暴走】小火苗申请升职为篝火，审批结果：先把今天的班值好。🔥",
        "【虚构事件·随机奖励】获得虚拟道具「发呆通行证」一张，有效期五分钟，无需兑换。🔥",
        "【虚构事件·补丁公告】修复了“今天又忘记喝水”的潜在问题。请自行完成最后一步。🔥",
        "【虚构事件·天气异常】营地局部下起爆米花雨，松鼠已携碗到场。🔥",
        "【虚构事件·背包整理】发现木柴×1、空气×99、找了三天的想象力×1。🔥",
        "【虚构事件·支线任务】帮助一块石头晒太阳。石头表示：躺着就行。🔥",
        "【虚构事件·服务器维护】烦恼服务器休息五分钟，零食服务器正常营业。🔥",
        "【虚构事件·营地广播】一只蘑菇误入会议，因全程安静获评最佳听众。🔥",
        "【虚构事件·随机掉落】获得虚拟称号「平平无奇添柴员」。无属性加成，但字数很多。🔥",
        "【虚构事件·火苗出差】目的地：隔壁烤炉。出差事由：学习如何把土豆烤得更香。🔥",
        "【虚构事件·地图更新】新增地点「沙发角落」，推荐装备：抱枕，推荐动作：休息。🔥",
    ),
    "easter_egg": (
        "【稀有彩蛋·开发者房间】\n你发现了隐藏按钮。\n按下后，出现一行小字：\n“这里没有捷径，只有一只正在烤土豆的鸭子。”\n鸭子：嘎。🔥",
        "【稀有彩蛋·史诗掉落】\n获得虚拟装备：平底锅形状的盾牌。\n防御力：未知。\n煎蛋能力：非常明确。\n装备说明：吃饱再去打副本。🔥",
        "【稀有彩蛋·宇宙回复】\n向宇宙提交了一个问题：今天吃什么？\n三秒后收到回执：\n“该问题超出当前宇宙算力，请咨询楼下饭馆。”🔥",
        "【稀有彩蛋·终极 BOSS】\n最终关卡的大门缓缓打开。\n里面坐着星期一，正和闹钟下棋。\n你悄悄给营地添了根柴，决定先存档。🔥",
        "【稀有彩蛋·隐藏成就】\n解锁虚拟称号「见过这条消息的人」。\n获取条件：见过这条消息。\n成就系统：逻辑闭环，十分满意。🔥",
        "【稀有彩蛋·片尾字幕】\n主演：一根柴。\n灯光：一团火。\n音效：噼里啪啦。\n特别鸣谢：路过但没有抢戏的土豆。🔥",
    ),
}

CATEGORY_WEIGHTS = {"literary": 30, "daily": 35, "roleplay": 24, "event": 10, "easter_egg": 1}
MAX_CHARS = 360
MAX_LINES = 18
# Conservative veto of romance, flirting, gendered relationship cues and heart symbols.
FORBIDDEN = (
    "恋", "暧昧", "情侣", "爱", "亲", "吻", "抱抱", "拥抱", "宝贝", "宝宝",
    "想你", "念你", "思念", "相思", "心动", "心跳", "心上", "心仪", "比心",
    "约会", "脱单", "表白", "告白", "情话", "情书", "情人", "情缘", "深情",
    "钟情", "倾心", "余生", "白头", "终老", "天长地久", "朝朝暮暮", "不离不弃",
    "男友", "女友", "男朋友", "女朋友", "老公", "老婆", "夫君", "娘子",
    "异性", "撩", "陪你", "等你", "只对你", "只为你", "唯一的你", "命中注定",
    "执子之手", "与子偕老", "❤️", "❤", "♥", "💕", "💞", "💓", "💗", "💖",
    "💘", "💝", "💋", "😘", "🥰", "😍", "🫶", "💑", "💏", "love", "kiss",
)


def is_safe_message(text: object) -> bool:
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_CHARS:
        return False
    if len(text.splitlines()) > MAX_LINES:
        return False
    # Collapse spaces and invisible characters so a split forbidden phrase is rejected too.
    normalized = unicodedata.normalize("NFKC", text).casefold()
    compact = "".join(c for c in normalized if not c.isspace() and unicodedata.category(c) != "Cf")
    return not any(word in compact for word in FORBIDDEN)


def _seed(value: str) -> int:
    return int.from_bytes(hashlib.sha256(value.encode("utf-8")).digest(), "big")


def generate_message(*, run_date: str | None = None, context: str = "") -> str:
    """Stable per date/recipient; no global random seed or stored state required.

    Weighted category draw gives eggs a 1% chance. Each category has a recipient-
    specific shuffled rotation indexed by day, avoiding identical consecutive-day
    copy even when the category repeats. Different recipients can still coincide.
    """
    day = date.fromisoformat(run_date) if run_date is not None else datetime.now(ZoneInfo("Asia/Shanghai")).date()
    rng = random.Random(_seed(f"{context}|{day.isoformat()}"))
    category = rng.choices(tuple(CATEGORY_WEIGHTS), weights=tuple(CATEGORY_WEIGHTS.values()), k=1)[0]
    candidates = [text for text in BANK[category] if is_safe_message(text)]
    if not candidates:
        raise ValueError("No reviewed copy available")
    random.Random(_seed(f"{context}|{category}")).shuffle(candidates)
    return candidates[day.toordinal() % len(candidates)]
