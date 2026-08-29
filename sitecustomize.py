"""PRODUCT HUNTER V5 runtime lexicon extensions.

Python imports sitecustomize automatically at startup. We use that hook to extend
analyzer.py without duplicating its scoring code. This keeps the V5 zero-credit
engine multilingual while the local embedding benchmark is still pending.
"""

try:
    import analyzer

    EXTRA_STOPWORDS = {
        "jeg","du","vi","det","den","som","med","på","av","fra","har","kan","bare","eller",
        "jeg","dig","vi","det","der","som","med","på","af","fra","har","kan","bare","eller",
        "ich","du","wir","es","das","der","die","mit","auf","von","aus","haben","kann","nur","oder",
        "ik","jij","wij","het","dit","dat","met","op","van","uit","hebben","kan","alleen","of",
        "minä","sinä","me","tämä","se","joka","kanssa","on","ovat","voi","vain","tai","myös",
    }
    analyzer.STOPWORDS.update(EXTRA_STOPWORDS)

    EXTRA_LEX = {
        "pain": [
            "smerte","vond","stiv","ubehag","vanskelig","plagsomt","lekker","rot","skitt","tungt",
            "smerte","ondt","stiv","ubehag","svært","besværligt","lækker","rod","snavs","tungt",
            "schmerz","schmerzen","steif","unangenehm","schwierig","lästig","leckt","unordnung","schmutz","anstrengend",
            "pijn","pijnlijk","stijf","ongemakkelijk","moeilijk","vervelend","lekt","rommel","vuil","zwaar",
            "kipu","särky","jäykkä","epämukava","vaikea","hankala","vuotaa","sotku","lika","raskas",
        ],
        "severity": [
            "hver natt","hver morgen","hele tiden","kan ikke","vanskelig å sove","hindrer meg",
            "hver nat","hver morgen","hele tiden","kan ikke","svært ved at sove","forhindrer",
            "jede nacht","jeden morgen","die ganze zeit","kann nicht","schwer zu schlafen","hindert mich",
            "elke nacht","elke ochtend","de hele tijd","kan niet","moeilijk slapen","houdt me tegen",
            "joka yö","joka aamu","koko ajan","en voi","vaikea nukkua","estää",
        ],
        "frequency": [
            "hver natt","hver morgen","hver gang","hele tiden","ofte","stadig","tilbakevendende",
            "hver nat","hver morgen","hver gang","hele tiden","ofte","konstant","tilbagevendende",
            "jede nacht","jeden morgen","jedes mal","ständig","oft","wiederkehrend",
            "elke nacht","elke ochtend","elke keer","altijd","vaak","constant","terugkerend",
            "joka päivä","joka yö","joka aamu","joka kerta","jatkuvasti","usein","toistuva",
        ],
        "relief": [
            "slipp","endelig","aldri mer","lettere","enklere","mer komfortabel","spar tid","uten stress",
            "slip for","endelig","aldrig mere","lettere","nemmere","mere behagelig","spar tid","uden besvær",
            "endlich","nie wieder","leichter","einfacher","bequemer","zeit sparen","ohne aufwand","ohne stress",
            "eindelijk","nooit meer","makkelijker","eenvoudiger","comfortabeler","tijd besparen","zonder gedoe",
            "vihdoin","ei enää","helpompi","mukavampi","säästä aikaa","ilman vaivaa","vähemmän vaivaa",
        ],
        "clarity": [
            "på sekunder","enkelt","automatisk","uten verktøy","med ett trykk",
            "på få sekunder","nemt","automatisk","uden værktøj","med ét tryk",
            "in sekunden","einfach","automatisch","ohne werkzeug","mit einem druck",
            "in seconden","eenvoudig","automatisch","zonder gereedschap","met één druk",
            "sekunneissa","helposti","automaattisesti","ilman työkaluja","yhdellä painalluksella",
        ],
        "evergreen": [
            "hjem","kjøkken","bad","soverom","hage","søvn","rengjøring","oppbevaring","orden","rygg","nakke","kne","ledd","kjæledyr",
            "hjem","køkken","badeværelse","soveværelse","have","søvn","rengøring","opbevaring","orden","ryg","nakke","knæ","led","kæledyr",
            "zuhause","küche","badezimmer","schlafzimmer","auto","garten","schlaf","reinigung","aufbewahrung","ordnung","rücken","nacken","knie","gelenk","haustier",
            "huis","keuken","badkamer","slaapkamer","auto","tuin","slaap","schoonmaak","opslag","orde","rug","nek","knie","gewricht","huisdier",
            "koti","keittiö","kylpyhuone","makuuhuone","auto","puutarha","uni","siivous","säilytys","järjestys","selkä","niska","polvi","nivel","lemmikki",
        ],
        "age35": [
            "rygg","nakke","kne","ledd","stiv","søvn","ergonomisk","grep","løfte","bøye",
            "ryg","nakke","knæ","led","stiv","søvn","ergonomisk","greb","løfte","bøje",
            "rücken","nacken","knie","gelenk","steif","schlaf","ergonomisch","griff","heben","bücken",
            "rug","nek","knie","gewricht","stijf","slaap","ergonomisch","grip","tillen","buigen",
            "selkä","niska","polvi","nivel","jäykkä","uni","ergonominen","ote","nostaa","kumartua",
        ],
        "trend": [
            "viral på tiktok","trendprodukt","hype produkt","samleobjekt",
            "viral på tiktok","trendprodukt","hype","samleobjekt",
            "tiktok viral","trendprodukt","hype produkt","sammelobjekt",
            "tiktok viraal","trendproduct","hype product","verzamelobject",
            "tiktok viraali","trendituote","hype tuote","keräilyesine",
        ],
        "claims": [
            "kurerer","behandler","helbreder","garantert resultat","mirakel","klinisk bevist",
            "kurerer","behandler","helbreder","garanteret resultat","mirakel","klinisk bevist",
            "heilt","behandelt","garantiertes ergebnis","wunder","klinisch bewiesen",
            "geneest","behandelt","gegarandeerd resultaat","wondermiddel","klinisch bewezen",
            "parantaa","hoitaa","taattu tulos","ihme","kliinisesti todistettu",
        ],
        "value": [
            "spar tid","spar penger","gjenbrukbar","holdbar","erstatter",
            "spar tid","spar penge","genanvendelig","holdbar","erstatter",
            "zeit sparen","geld sparen","wiederverwendbar","langlebig","ersetzt",
            "tijd besparen","geld besparen","herbruikbaar","duurzaam","vervangt",
            "säästä aikaa","säästä rahaa","uudelleenkäytettävä","kestävä","korvaa",
        ],
        "demo": [
            "før og etter","se forskjellen","slik fungerer det","på sekunder",
            "før og efter","se forskellen","sådan virker det","på få sekunder",
            "vorher nachher","sieh den unterschied","so funktioniert es","in sekunden",
            "voor en na","zie het verschil","zo werkt het","in seconden",
            "ennen ja jälkeen","näe ero","näin se toimii","sekunneissa",
        ],
        "broad": [
            "hjem","søvn","rengjøring","kjøkken","bil","hage","oppbevaring","komfort","rygg","nakke",
            "hjem","søvn","rengøring","køkken","bil","have","opbevaring","komfort","ryg","nakke",
            "zuhause","schlaf","reinigung","küche","auto","garten","aufbewahrung","komfort","rücken","nacken",
            "huis","slaap","schoonmaak","keuken","auto","tuin","opslag","comfort","rug","nek",
            "koti","uni","siivous","keittiö","auto","puutarha","säilytys","mukavuus","selkä","niska",
        ],
        "commodity": [
            "usb-kabel","telefondeksel","vannflaske","lader","solbriller",
            "usb-kabel","telefoncover","vandflaske","oplader","solbriller",
            "usb kabel","handyhülle","wasserflasche","ladegerät","sonnenbrille",
            "usb kabel","telefoonhoesje","waterfles","oplader","zonnebril",
            "usb kaapeli","puhelinkuori","vesipullo","laturi","aurinkolasit",
        ],
    }

    for key, terms in EXTRA_LEX.items():
        if key in analyzer.LEX:
            analyzer.LEX[key].extend(x for x in terms if x not in analyzer.LEX[key])

    CATEGORY_EXTRA = {
        "Sömn": ["søvn","sove","pute","madrass","snork","søvn","sove","pude","madras","snork","schlaf","kissen","matratze","schnarch","slaap","kussen","matras","snurk","uni","nukkua","tyyny","patja","kuorsaus"],
        "Rygg & komfort": ["rygg","nakke","kne","ledd","ryg","nakke","knæ","led","rücken","nacken","knie","gelenk","rug","nek","knie","gewricht","selkä","niska","polvi","nivel"],
        "Städning": ["rengjøring","skitt","støv","mopp","børste","rengøring","snavs","støv","moppe","børste","reinigung","schmutz","staub","mopp","bürste","schoonmaak","vuil","stof","dweil","borstel","siivous","lika","pöly","moppi","harja"],
        "Förvaring & ordning": ["oppbevaring","orden","rot","opbevaring","orden","rod","aufbewahrung","ordnung","unordnung","opslag","orde","rommel","säilytys","järjestys","sotku"],
        "Kök": ["kjøkken","mat","oppvask","køkken","mad","opvask","küche","essen","geschirr","keuken","eten","afwas","keittiö","ruoka","astianpesu"],
        "Bil": ["bil","sete","frontrute","bil","sæde","forrude","auto","sitz","windschutzscheibe","auto","stoel","voorruit","auto","istuin","tuulilasi"],
        "Trädgård": ["hage","plen","plante","have","græsplæne","plante","garten","rasen","pflanze","tuin","gazon","plant","puutarha","nurmikko","kasvi"],
        "Husdjur": ["hund","katt","kjæledyr","hund","kat","kæledyr","hund","katze","haustier","hond","kat","huisdier","koira","kissa","lemmikki"],
        "Badrum": ["bad","dusj","toalett","badeværelse","bruser","toilet","badezimmer","dusche","toilette","badkamer","douche","toilet","kylpyhuone","suihku","wc"],
        "Kläder & skor": ["sko","klær","sokk","sko","tøj","sok","schuh","kleidung","socke","schoen","kleding","sok","kenkä","vaate","sukka"],
        "Hem & vardag": ["hjem","hverdag","hjem","hverdag","zuhause","alltag","huis","dagelijks","koti","arki"],
    }
    for label, words in analyzer.CATEGORIES:
        for term in CATEGORY_EXTRA.get(label, []):
            if term not in words:
                words.append(term)

    PROBLEM_EXTRA = {
        "Smärta/obehag": ["smerte","stiv","ubehag","smerte","stiv","ubehag","schmerz","steif","unangenehm","pijn","stijf","ongemakkelijk","kipu","särky","jäykkä","epämukava"],
        "Sömnproblem": ["søvn","våkner","snork","søvn","vågner","snork","schlaf","aufwachen","schnarch","slaap","wakker","snurk","uni","herää","kuorsaus"],
        "Stök/ordning": ["rot","oppbevaring","orden","rod","opbevaring","orden","unordnung","aufbewahrung","ordnung","rommel","opslag","orde","sotku","säilytys","järjestys"],
        "Tidskrävande vardag": ["tar tid","spar tid","kronglete","tager tid","spar tid","besværligt","zeitaufwendig","zeit sparen","aufwand","kost tijd","tijd besparen","gedoe","vie aikaa","säästä aikaa","vaivalloinen"],
        "Städ/smuts": ["rengjøring","skitt","støv","mugg","rengøring","snavs","støv","skimmel","reinigung","schmutz","staub","schimmel","schoonmaak","vuil","stof","schimmel","siivous","lika","pöly","home"],
        "Spill/läckage": ["søl","lekker","spild","lækker","verschütten","leck","morsen","lekt","läikkyy","vuotaa"],
        "Lyft/böj/rörelse": ["bøye","løfte","grep","bøje","løfte","greb","bücken","heben","griff","buigen","tillen","grip","kumartua","nostaa","ote"],
        "Husdjur": ["hund","katt","kjæledyr","hund","kat","kæledyr","hund","katze","haustier","hond","kat","huisdier","koira","kissa","lemmikki"],
    }
    for label, words in analyzer.PROBLEMS:
        for term in PROBLEM_EXTRA.get(label, []):
            if term not in words:
                words.append(term)

except Exception:
    # Never let a lexicon extension stop the app from starting.
    pass
