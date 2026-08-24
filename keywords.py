COUNTRY_STRATEGIES = {
    "SE": {"name":"Sverige","keywords":[
        "trött på","slipp","svårt att","vaknar med","ont i","ont när","varje dag",
        "äntligen","utan att behöva","slipp böja dig","spara tid","slipp stök",
        "gör vardagen enklare","för dig som","aldrig mer","bekvämare hemma",
        "håller ordning","tar för mycket tid","problem med","lösningen för"
    ]},
    "NO": {"name":"Norge","keywords":[
        "lei av","slipp","vanskelig å","våkner med","vondt i","hver dag","endelig",
        "uten å måtte","slipp å bøye deg","spar tid","mindre rot","gjør hverdagen enklere",
        "for deg som","aldri mer","mer komfort hjemme","problem med"
    ]},
    "DK": {"name":"Danmark","keywords":[
        "træt af","slip for","svært ved","vågner med","ondt i","hver dag","endelig",
        "uden at skulle","slip for at bøje dig","spar tid","mindre rod",
        "gør hverdagen lettere","til dig der","aldrig mere","problem med"
    ]},
    "FI": {"name":"Finland","keywords":[
        "helpompi arki","vaikea","joka päivä","vihdoin","säästä aikaa","parempi uni",
        "helpompi kotona","arkiongelma","ilman että","mukavampi","vähemmän vaivaa"
    ]},
    "DE": {"name":"Tyskland","keywords":[
        "müde von","schwer zu","jeden tag","endlich","ohne zu müssen","zeit sparen",
        "besser schlafen","ordnung halten","alltag leichter","weniger aufwand","problem mit"
    ]},
    "NL": {"name":"Nederländerna","keywords":[
        "moe van","moeilijk om","elke dag","eindelijk","zonder gedoe","tijd besparen",
        "beter slapen","opgeruimd huis","dagelijks leven makkelijker","probleem met"
    ]},
    "AT": {"name":"Österrike","keywords":[
        "müde von","schwer zu","jeden tag","endlich","ohne aufwand","zeit sparen",
        "besser schlafen","alltag leichter","problem mit"
    ]},
    "CH": {"name":"Schweiz","keywords":[
        "müde von","schwer zu","jeden tag","endlich","ohne aufwand","zeit sparen",
        "mehr komfort","alltag leichter","problem mit"
    ]},
}
DEFAULT_ORDER = ["SE","NO","DK","FI","DE","NL","AT","CH"]

def next_keyword(country_code, index):
    s = COUNTRY_STRATEGIES.get(country_code, COUNTRY_STRATEGIES["SE"])
    words = s["keywords"]
    return words[index % len(words)]
