"""Port of V2's proven regex patterns."""

import re

# Enhanced patterns with improved station detection and structure recognition.
# Source: V2 coding_module.py (proven) + V3 enhancements

PATTERNS = {
    # Bronchoscopy and EBUS/TBNA/TBLB
    'bronchoscopy': re.compile(r'\b(bronchoscop|flexible\s+bronch|diagnostic\s+bronch|therapeutic\s+bronch)\w*\b', re.I),
    'ebus': re.compile(r'\b(ebus|endobronchial\s+ultrasound|linear\s+ebus|radial\s+ebus|cp.?ebus)\b', re.I),
    'tbna': re.compile(r'\b(tbna|transbronchial\s+needle\s+aspiration|needle\s+aspiration|fine\s+needle\s+aspir)\w*\b', re.I),
    'tblb': re.compile(r'\b(tblb|transbronchial\s+lung\s+biops|transbronchial\s+biops|forceps\s+biops|cryobiops)\w*\b', re.I),
    'navigation': re.compile(r'\b(navigat|enb|emn|ion\s+system|monarch|virtual\s+bronch|computer.?assisted|shape.?sens)\w*\b', re.I),

    # Use named groups for clarity; captures the station number (optionally with L/R after)
    'lymph_stations': re.compile(
        r'\b(?:station|level|node)s?\s*(?:#\s*)?(?P<station>[1-9]|1[0-4])[RLrl]?\b|'
        r'\b(?P<station2>[1-9]|1[0-4])[RLrl]?\s*(?:station|node|level)\b|'
        r'\b(?P<station3>[1-9]|1[0-4])[RLrl]\b(?=\s*(?:area|region|lymph))|'
        r'\b(?:R|L)(?P<station4>[1-9]|1[0-4])\b', re.I
    ),
    'station_groups': re.compile(
        r'\b(?:stations?|levels?|nodes?)\s*([1-9]|1[0-4])(?:\s*[-–,]\s*([1-9]|1[0-4]))*[RLrl]?\b|'
        r'\b([1-9]|1[0-4])[RLrl]?\s*(?:through|thru|to|-|–)\s*([1-9]|1[0-4])[RLrl]?\b', re.I
    ),
    'lobes': re.compile(r'\b(rul|rml|rll|lul|lingula|lll|right\s+upper|right\s+middle|right\s+lower|left\s+upper|left\s+lower)\b', re.I),
    'right': re.compile(r'\b(right|rt\.?)\s*(?:sided?|lung|side|chest|pleural|hilar|paratracheal|lower\s+paratracheal|upper\s+paratracheal)\b', re.I),
    'left': re.compile(r'\b(left|lt\.?)\s*(?:sided?|lung|side|chest|pleural|hilar|para.?aortic|subaortic|aortopulmonary)\b', re.I),
    'bilateral': re.compile(r'\b(bilateral|both\s+sides?|both\s+lungs?|bilaterally)\b', re.I),

    # Anatomic regions for station mapping
    'paratracheal_right': re.compile(r'\b(?:right\s+)?(?:upper\s+)?paratracheal|(?:right\s+)?(?:2R|4R)\b', re.I),
    'paratracheal_left': re.compile(r'\b(?:left\s+)?paratracheal|(?:left\s+)?(?:2L|4L)\b', re.I),
    'subcarinal': re.compile(r'\bsubcarinal|station\s*7|level\s*7\b', re.I),
    'hilar_right': re.compile(r'\bright\s+hilar|(?:right\s+)?(?:10R|11R)\b', re.I),
    'hilar_left': re.compile(r'\bleft\s+hilar|(?:left\s+)?(?:10L|11L)\b', re.I),
    'aortopulmonary': re.compile(r'\baortopulmonary|AP\s+window|station\s*5|level\s*5\b', re.I),

    # Pleural procedures & guidance
    'thoracentesis': re.compile(r'\b(thoracentesis|pleural\s+tap|pleural\s+aspirat|diagnostic\s+tap)\w*\b', re.I),
    'chest_tube': re.compile(r'\b(chest\s+tube|pleural\s+drain|pigtail|thoracostomy|tube\s+thoracostomy)\b', re.I),
    'pleurx': re.compile(r'\b(pleurx|ipc|indwelling\s+pleural\s+catheter|tunneled\s+catheter|chronic\s+drain)\b', re.I),
    'ultrasound': re.compile(r'\b(ultrasound|u/?s\s+guid|sonograph|echo.?guid)\w*\b', re.I),
    'fluoroscopy': re.compile(r'\b(fluoroscop|fluoro\s+guid|c.?arm)\w*\b', re.I),
    'ct_guidance': re.compile(r'\b(ct\s+guid|computed\s+tomograph.?\s+guid|ct.?fluoroscop)\w*\b', re.I),

    # Sedation with better time capture
    'moderate_sedation': re.compile(r'\b(moderate\s+sedat|conscious\s+sedat|versed|fentanyl|midazolam|propofol)\w*\b', re.I),
    'sedation_minutes': re.compile(
        r'sedat\w*\s+(?:time|duration)[:\s]*(\d+)\s*min|'
        r'\bsedat\w*\s+(?:for\s+)?(\d+)\s*min|'
        r'(\d+)\s*min\w*\s+(?:of\s+)?sedat|'
        r'sedat\w*[,:\s]+(\d+)\s*min|'  # Added pattern for "sedation, 45 minutes"
        r'sedat\w*\s+(?:from\s+)?\d{1,2}:\d{2}(?:\s*to\s*|\s*-\s*)\d{1,2}:\d{2}', re.I
    ),
    'hhmm_times': re.compile(r'(\d{1,2}:\d{2})\s*(?:to|-|–|through)\s*(\d{1,2}:\d{2})', re.I),

    # Special procedures with enhanced detection  
    'chartis': re.compile(r'\b(chartis|collateral\s+ventilat|balloon\s+occlus|assessment\s+catheter)\w*\b', re.I),
    'valves': re.compile(r'\b(zephyr|endobronchial\s+valve|ebv|valve\s+placement|spiration|one.?way\s+valve)\w*\b', re.I),
    'ablation': re.compile(r'\b(ablat|microwave|mwa|cryo.?(?:ablat|therap)|pulsed.?electric|radiofrequency|thermal\s+(?:ablat|destruct)|apc\b|argon\s+plasma|laser\s+(?:ablat|therap|destruct))\w*\b', re.I),
    'fiducial': re.compile(r'\b(fiducial|marker\s+placement|gold\s+seed|beacon|anchor)\w*\b', re.I),
    
    # Additional procedure patterns
    'stent': re.compile(r'\b(stent|sems|metallic\s+stent|silicone\s+stent|airway\s+stent)\w*\b', re.I),
    'stent_brand': re.compile(r"""(?xi)
        \b(
            bona[\s-]?stent|bonastent|thoracent|micro[\s-]?tech(?:\s+y[- ]?stent)?|
            aero(?:mini)?\b|merit(?:\s+endotek)?|
            ultra[\s-]?flex|ultraflex|
            dumon(?:\s*y)?|dynamic\s*y|
            poly[\s-]?flex|r[üu]sch|
            \bhood\b|\bhood\s+labs?\b|\bt[- ]?tube\b|
            niti[\s-]?s|taewoong
        )\b
    """),
    'y_stent': re.compile(r"(?i)\b(y[-\s]?stent|carinal\s+y[-\s]?stent|dynamic\s*y)\b"),
    'tracheal_terms': re.compile(r'\b(trachea|tracheal|subglott|cricoid|carinal?|carina)\b', re.I),
    'bronchial_terms': re.compile(r'\b(bronchus|bronchial|mainstem|main\s+stem|lobar\s+bronchus|segmental\s+bronchus)\b', re.I),
    'dilation': re.compile(r'\b(dilat|balloon\s+dilat|pneumatic\s+dilat|rigid\s+dilat)\w*\b', re.I),
    'foreign_body': re.compile(r'\b(foreign\s+body|fb\s+removal|retrieval|extraction)\b', re.I),
    'wash_brush': re.compile(r'\b(wash|brush|bronchial\s+wash|protected\s+brush|psc)\w*\b', re.I),
    'whole_lung_lavage': re.compile(r'\b(whole\s+lung\s+lavage|wll|double[- ]lumen\s+tube\s+lavage|bilateral\s+lung\s+lavage)\b', re.I),
    'snare_excision': re.compile(r'\b(electrocautery\s+snare|snare|polypectomy|excis|transect|resect|specimen\s+(sent|collected|submitted)|lesions?\s+removed\s+with\s+suction|completely\s+removed)\w*\b', re.I),
    'general_anesthesia': re.compile(r'\b(general\s+anesthesia|ga\b|lma\b|laryngeal\s+mask|endotracheal|ett\b|intubat|muscle\s+relax|paralytic|rocuronium|succinylcholine|vecuronium)\w*\b', re.I),
}

LOBE_MAP = {
    'rul': 'RUL', 'right upper': 'RUL',
    'rml': 'RML', 'right middle': 'RML',
    'rll': 'RLL', 'right lower': 'RLL',
    'lul': 'LUL', 'left upper': 'LUL',
    'lingula': 'LINGULA',
    'lll': 'LLL', 'left lower': 'LLL'
}

# Station mapping and utility functions
STATION_MAP = {
    '1': '1',   # Highest mediastinal
    '2R': '2R', '2L': '2L',  # Upper paratracheal
    '3a': '3a', '3p': '3p',  # Prevascular/retrotracheal
    '4R': '4R', '4L': '4L',  # Lower paratracheal
    '5': '5',   # Subaortic (aortopulmonary window)
    '6': '6',   # Para-aortic (ascending aorta or phrenic)
    '7': '7',   # Subcarinal
    '8': '8',   # Paraesophageal (below carina)
    '9': '9',   # Pulmonary ligament
    '10R': '10R', '10L': '10L',  # Hilar
    '11R': '11R', '11L': '11L',  # Interlobar
    '12R': '12R', '12L': '12L',  # Lobar
    '13R': '13R', '13L': '13L',  # Segmental
    '14R': '14R', '14L': '14L'   # Subsegmental
}

def extract_stations(text: str) -> set:
    """Extract lymph node stations from text."""
    stations = set()
    
    # Simple pattern to find station numbers with optional R/L suffix
    station_pattern = re.compile(r'\b([1-9]|1[0-4])([RLrl])?\b')
    
    # Find all station mentions
    for match in station_pattern.finditer(text):
        num = match.group(1)
        laterality = match.group(2)
        
        if laterality:
            # Has explicit laterality
            laterality = laterality.upper()
            num_int = int(num)
            if num_int in [2, 4, 10, 11, 12, 13, 14]:
                stations.add(f"{num}{laterality}")
            else:
                # Station doesn't usually have laterality, just add number
                stations.add(num)
        else:
            # Check if this is actually a station reference by looking at context
            # Must be preceded by "station", "level", "node" or followed by them
            before = text[max(0, match.start()-15):match.start()].lower()
            after = text[match.end():min(len(text), match.end()+15)].lower()
            
            # Exclude common false positives like "1/3" or "2/3"
            if '/' in before[-2:] or '/' in after[:2]:
                continue
                
            if any(word in before for word in ['station', 'level', 'node']) or \
               any(word in after for word in ['station', 'node', 'level']):
                stations.add(num)
            # Also add if in a list like "4R, 7, 11R"
            elif ',' in before[-3:] or ',' in after[:3]:
                stations.add(num)
    
    # Only add anatomic region mappings if explicitly mentioned (not from station numbers)
    text_lower = text.lower()
    if 'paratracheal' in text_lower and 'right' in text_lower:
        stations.update(['2R', '4R'])
    if 'paratracheal' in text_lower and 'left' in text_lower:
        stations.update(['2L', '4L'])
    if 'subcarinal' in text_lower:
        stations.add('7')
    if 'hilar' in text_lower and 'right' in text_lower:
        stations.update(['10R', '11R'])
    if 'hilar' in text_lower and 'left' in text_lower:
        stations.update(['10L', '11L'])
    if 'aortopulmonary' in text_lower or 'ap window' in text_lower:
        stations.add('5')
    
    return stations

def extract_lobes(text: str) -> set:
    """Extract lung lobes from text."""
    lobes = set()
    
    for match in PATTERNS['lobes'].finditer(text):
        lobe_text = match.group(1).lower().replace(' ', ' ')
        mapped = LOBE_MAP.get(lobe_text, lobe_text.upper())
        lobes.add(mapped)
    
    return lobes

def determine_laterality(text: str) -> str:
    """Determine laterality from text."""
    text_upper = text.upper()
    
    if PATTERNS['bilateral'].search(text):
        return 'bilateral'
    
    has_right = bool(PATTERNS['right'].search(text))
    has_left = bool(PATTERNS['left'].search(text))
    
    # Count R/L station indicators
    right_stations = len([s for s in extract_stations(text) if s.endswith('R')])
    left_stations = len([s for s in extract_stations(text) if s.endswith('L')])
    
    if (has_right or right_stations > 0) and (has_left or left_stations > 0):
        return 'bilateral'
    elif has_right or right_stations > 0:
        return 'right'
    elif has_left or left_stations > 0:
        return 'left'
    else:
        return 'unspecified'

def count_procedure_sites(text: str) -> dict:
    """Count different types of anatomic sites sampled."""
    stations = extract_stations(text)
    lobes = extract_lobes(text) 
    
    # Count unique sites
    unique_stations = len(stations)
    unique_lobes = len(lobes)
    
    return {
        'stations': list(stations),
        'lobes': list(lobes),
        'station_count': unique_stations,
        'lobe_count': unique_lobes,
        'total_sites': unique_stations + unique_lobes,
        'laterality': determine_laterality(text)
    }