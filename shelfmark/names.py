"""Распознавание имён людей в строках титульных страниц.

Заголовок «DARK MATTER» и подпись автора «BLAKE CROUCH» на обложке
выглядят одинаково (2 слова ЗАГЛАВНЫМИ). Разделяем их по словарю
распространённых имён: если одно из слов строки — известное имя,
строка скорее подпись автора.
"""

from __future__ import annotations

import re

_RU_FIRST_NAMES = frozenset("""
александр алексей алина алла анастасия андрей анна антон аркадий артур
борис богдан вадим валерий валерия варвара василий вера вероника виктор
виктория виталий владимир владислав галина геннадий георгий григорий дарья
денис дмитрий ева евгений евгения егор екатерина елена елизавета жанна
зинаида игорь иван илья инна ирина кирилл константин ксения лариса лев
леонид лидия любовь людмила маргарита марина мария михаил
надежда наталья никита николай нина оксана олег ольга павел пётр петр
полина роман руслан светлана семён сеня сергей софия софья станислав
степан тамара тарас татьяна тимур тимофей ульяна фёдор федор филипп
эдуард юлия юрий яков яна ярослав джоан джоанна джордж
# транслитерации частых английских имён (книги в переводе)
уильям джон джеймс роберт майкл дэвид эдвард томас ричард чарльз
дэниел дэниэл мэтью мартин брайан брюс винсент гарри герберт деннис
джеральд джозеф джонатан дуглас итан кеннет кевин лоуренс леонард
малкольм николас марк оливер патрик питер рональд стэнли стивен
теренс теодор франклин фредерик гарольд эндрю альберт арчибальд гас
элизабет дженнифер джессика кэтрин кэти мэри сара джейн лора эмма
линда маргарет моника нэнси патриция ребекка розмари сьюзан тереза
алиса аманда барбара бренда дебора диана дорис джудит кэрол
натали хелен хизер шерон ширли дебби
""".split())

_EN_FIRST_NAMES = frozenset("""
aaron adam alan albert alex alexander alice amanda amy andrew angela
anna anthony arthur audrey barbara barry benjamin bernard betty beverly
blake brandon brenda brian bruce bryan carol carter catherine cathy
charles charlotte cheryl chris christian christina christine christopher
cindy claire clarence clifford colin colleen connor cody craig cynthia
dale daniel danielle darren david dean deborah debra dennis derek diana
diane donald donna doris dorothy douglas dylan earl edgar edith edward
edwin eleanor elena elizabeth ellie ellen emily emma eric erica ernest
esther eugene evan evelyn fiona florence frances frank franklin
frederick gabriel gary george gerald gina gilbert glenn grace gregory
hannah harold harriet harry harvey heather helen henry herbert howard
hugh ian irene isaac isabel ivan jack jacob james jane janet janice
jared jason jay jean jeffrey jennifer jeremy jerry jessica jill joan
joanne joe joel john johnny jonathan jordan joseph joshua joyce judith
julia julian julie justin karen karl katherine kathleen kathryn kathy
keith kelly kenneth kevin kimberly kurt kyle larry laura lauren lawrence
leonard leslie lewis liam linda lisa lloyd logan lois louis louise lucas
luke lydia lynn madison malcolm marcus margaret maria marie marilyn mark
martha martin mary matthew maureen max megan melanie melissa michael
michelle mildred monica natalie nathan neil nelson nicholas nicole nigel
nina nora norman oliver oscar owen pamela patricia patrick paul paula
pedro peggy peter philip phoebe phyllis quentin rachel ralph randall
raymond rebecca regina richard rita robert roberta robin rodney roger
roland ronald rosa rose ross roy russell ruth ryan sabrina samantha
samuel sandra sarah scott sean seth sharon sheila shirley sidney simon
sophia spencer stanley stephanie stephen steven stuart susan sylvia
tamara tanya teresa thomas timothy tina todd travis trevor tyler valerie
vanessa vera vernon veronica victor victoria vincent virginia vivian
walter wanda warren wayne wendy wesley william willie zachary zoe
""".split())

_FIRST_NAMES = _RU_FIRST_NAMES | _EN_FIRST_NAMES

_WORDS_RE = re.compile(r"[^\s,]+")


def is_person_name(text: str) -> bool:
    """Похожа ли строка на имя человека: «АРТУР ДУМЧЕВ», «by Jane Smith».

    Правила: 2–3 слова, среди них есть известное имя на первой или
    последней позиции, остальные слова — инициалы или с заглавной буквы.
    """
    t = text.strip().strip(",;:-–—")
    words = [w.strip(".,'’\"()") for w in _WORDS_RE.findall(t)]
    if not (2 <= len(words) <= 3) or any(not w for w in words):
        return False

    known_positions = [i for i, w in enumerate(words) if w.lower() in _FIRST_NAMES]
    if not known_positions:
        return False
    # имя должно быть первым или последним словом («ЧТО БУДЕТ» — не имя)
    if not any(i in (0, len(words) - 1) for i in known_positions):
        return False
    # остальные слова: инициалы («В.») или слова с заглавной буквы
    return all(len(w) <= 2 or w[0].isupper() for w in words)
