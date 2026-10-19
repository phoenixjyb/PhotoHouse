"""Conservative exclusion admission before literal planning or visual ranking.

An embedding similarity score cannot prove absence. These bounded bilingual
cues therefore require a complete revised request, except for an explicit
positive media type followed by its exact excluded counterpart. This is an
admission policy, not a general natural-language negation parser.
"""
import re
import unicodedata

EXCLUSION_POLICY_VERSION = 1

# ASCII boundaries keep Chinese/English combinations usable without matching
# e.g. notebook. Quoted scene wording is deliberately not opaque to this guard.
NEGATION = re.compile(
    r'(?a:\b)(?:no|not|never|without|except|excluding|exclude|neither|nor|'
    r'remove|delete|cannot|lacking|lacks?|absent|absence\s+of|'
    r'rather\s+than|instead\s+of|other\s+than|free\s+of)(?a:\b)|'
    r'(?a:\b)(?:don|doesn|didn|isn|aren|wasn|weren|hasn|haven|hadn|'
    r'can|couldn|wouldn|shouldn|mustn|won)[\x27’]t(?a:\b)|'
    r'(?a:\b)non[-\s]|[-]free(?a:\b)|'
    r'不要|没有|沒有|没在|沒在|没穿|沒穿|没戴|沒戴|没拿|沒拿|'
    r'不在|不是|不含|不包括|不包含|不带|不帶|不穿|不戴|不拿|不想|'
    r'不需要|不出现|不出現|排除|除外|删除|刪除|而非|并非|並非|'
    r'未曾|从未|從未|不曾|未见|未見|未带|未帶|未穿|未戴|'
    r'没(?!落)|沒(?!落)|看不到|看不见|看不見|缺少|缺乏|'
    r'无(?!锡)|無(?!錫)', re.I)


def requires_exclusion_clarification(value):
    return (type(value) is str and
            NEGATION.search(unicodedata.normalize('NFKC', value).casefold()) is not None)


def exclusion_reply(language, continuation=False, expired=False):
    if language == 'zh':
        lead = ('上次排除条件的确认已过期。' if expired else
                '上次的排除条件仍未解决。' if continuation else
                '这次查找包含尚无法可靠验证的排除条件。')
        return (lead + '你希望照片中明确出现什么？请发送完整的新查找句，明确保留、改写或取消排除条件，'
                '并写明仍需保留的人物、日期和媒体类型。不会把未识别或未检测到当作不存在，也不会忽略原条件。')
    lead = ('The previous exclusion confirmation has expired. ' if expired else
            'The previous exclusion is still unresolved. ' if continuation else
            'This search includes an exclusion I cannot reliably verify. ')
    return (lead + 'What should visibly appear? Send a complete revised search that explicitly keeps, '
            'changes, or removes the exclusion and includes any people, dates, and media type to retain. '
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
