"""Conservative exclusion admission before literal planning or visual ranking.

An embedding similarity score cannot prove absence. These bounded bilingual
cues therefore require a complete revised request, except for an explicit
positive media type followed by its exact excluded counterpart. This is an
admission policy, not a general natural-language negation parser.
"""
import re
import unicodedata

EXCLUSION_POLICY_VERSION = 2

# Keep negative predicates shared by request admission and affirmative evidence
# matching. Do not match a bare 不/未: lexical words such as 不倒翁/未来 are
# positive descriptions. 没落 can be lexical, but 没落在/没落到 is a predicate.
_CHINESE_NEGATIVE_PREDICATE = (
    r'(?:没|沒|不|未)(?:曾|能|在|有|是|去|到|下|穿|戴|拿|带|帶|看|吃|喝|'
    r'玩|跑|骑|騎|走|跳|打|吹|读|讀|写|寫|切|笑|见|見|出现|出現|'
    r'落在|落到|落地|倒在|倒到|抱|坐|站|躺|睡|游泳|飞|飛|撑|撐)'
)
_APOSTROPHE = r'[\x27’‘ʼ‛]'

# ASCII boundaries keep Chinese/English combinations usable without matching
# e.g. notebook. Quoted scene wording is deliberately not opaque to this guard.
NEGATION = re.compile(
    r'(?a:\b)(?:no|not|never|without|except|excluding|exclude|neither|nor|'
    r'remove|delete|cannot|lacking|lacks?|absent|absence\s+of|zero|none|'
    r'nobody|nothing|minus|devoid\s+of|'
    r'rather\s+than|instead\s+of|other\s+than|free\s+of)(?a:\b)|'
    r'(?a:\b)(?:don|doesn|didn|isn|aren|wasn|weren|hasn|haven|hadn|'
    r'can|couldn|wouldn|shouldn|mustn|won|ain|needn|mightn)' + _APOSTROPHE + r't(?a:\b)|'
    r'(?a:\b)non[-\s]|[-]free(?a:\b)|'
    r'(?<![a-z0-9])0(?=\s|[个個位人只辆輛棵条條件台对對])|'
    r'不要|没有|沒有|没在|沒在|没穿|沒穿|没戴|沒戴|没拿|沒拿|'
    r'不在|不是|不含|不包括|不包含|不带|不帶|不穿|不戴|不拿|不想|'
    r'不需要|不出现|不出現|排除|除外|删除|刪除|而非|并非|並非|'
    r'未曾|从未|從未|不曾|未见|未見|未带|未帶|未穿|未戴|'
    r'没(?!落)|沒(?!落)|看不到|看不见|看不見|缺少|缺乏|'
    r'无(?!锡)|無(?!錫)|'
    r'(?:别|別|甭)(?:带|帶|出现|出現|穿|戴|拿|放|拍|选|選)|'
    r'避开|避開|去掉|零(?:只|个|個|位|人|辆|輛)|' +
    _CHINESE_NEGATIVE_PREDICATE, re.I)

# Explicit precision/exclusivity is a hard condition, not an approximate scene
# clue. Ordinary positive counts remain a separate model-quality qualification.
_COUNT = (r'(?:[0-9]+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|'
          r'twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|'
          r'twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|'
          r'a\s+single|[零〇一二两兩三四五六七八九十百]+)')
_STRICT_COMPOSITION = re.compile(
    r'(?a:\b)(?:exactly|precisely|at\s+least|at\s+most|fewer\s+than|'
    r'more\s+than|less\s+than|a\s+single)(?a:\b)|'
    r'(?a:\b)(?:exactly|precisely|just)\s*' + _COUNT + r'(?![a-z0-9])|'
    r'(?a:\b)(?:alone|sole|solely|only)(?a:\b)|'
    r'只有|仅有|僅有|独自|獨自|单独|單獨|'
    r'(?:恰好|刚好|剛好|正好|至多|至少|最多|最少|多于|多於|少于|少於|仅仅|僅僅|仅|僅|只)\s*'
    r'[零〇一二两兩三四五六七八九十百0-9]+\s*(?:个|個|位|人|只|辆|輛|棵|条|條|件|台|对|對)', re.I)


def requires_exclusion_clarification(value):
    return (type(value) is str and
            NEGATION.search(unicodedata.normalize('NFKC', value).casefold()) is not None)


def requires_semantic_clarification(value):
    """Refuse known unsupported hard conditions before approximate ranking."""
    return (requires_exclusion_clarification(value) or
            (type(value) is str and _STRICT_COMPOSITION.search(
                unicodedata.normalize('NFKC', value).casefold()) is not None))


def exclusion_reply(language, continuation=False, expired=False):
    if language == 'zh':
        lead = ('上次严格画面条件的确认已过期。' if expired else
                '上次的排除或严格画面条件仍未解决。' if continuation else
                '这次查找包含尚无法可靠验证的排除或严格画面条件。')
        return (lead + '排除、独占或精确数量要求都需要可靠证据。你希望照片中明确出现什么？'
                '请发送完整的新查找句，明确保留、改写或取消这些条件，'
                '并写明仍需保留的人物、日期和媒体类型。不会把未识别或未检测到当作不存在，也不会忽略原条件。')
    lead = ('The previous strict scene condition confirmation has expired. ' if expired else
            'The previous exclusion or strict scene condition is still unresolved. ' if continuation else
            'This search includes an exclusion or strict scene condition I cannot reliably verify. ')
    return (lead + 'Exclusions, exclusivity, and exact counts need reliable evidence. '
            'What should visibly appear? Send a complete revised search that explicitly keeps, '
            'changes, or removes these conditions and includes any people, dates, and media type to retain. '
            'Missing labels or detections do not prove absence; the original condition will not be ignored.')


_IMAGE = r'(?:photos?|photographs?|pictures?|images?|照片|图片|相片)'
_VIDEO = r'(?:videos?|movies?|视频|影片)'
_END = r'\s*[。.!！?？]*\s*$'


def explicit_media_exclusion(value):
    """Mask only a closed trailing media exclusion with an explicit counterpart.

    Bare 'exclude videos' is not equivalent to images (other MIME types may
    exist). Return the original string when uncertain; the caller then refuses
    any remaining negation. Offsets refer to the caller's already folded text.
    """
    for positive, negative in ((_IMAGE, _VIDEO), (_VIDEO, _IMAGE)):
        pattern = re.compile(
            r'(?:[,，;；]\s*|\s+)(?:(?a:\b)(?:not|without|excluding|exclude)(?a:\b)\s*|不要|排除)'
            r'(?P<media>' + negative + r')' + _END, re.I)
        match = pattern.search(value)
        if match is None:
            continue
        before = value[:match.start()]
        # The positive noun must end as a noun, not "photojournalism".
        positive_pattern = re.compile(r'(?<![a-z])' + positive + r'(?![a-z])', re.I)
        if positive_pattern.search(before) and not requires_exclusion_clarification(before):
            return before + ' ' * (len(value) - len(before))
    return value
