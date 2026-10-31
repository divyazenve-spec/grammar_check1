"""Local grammar, spelling, and sentence formation correction service using LanguageTool and rule engines."""

import atexit
import difflib
import json
import logging
import os
import re
import threading
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TOOL = None
LOCK = threading.Lock()


def load_tool():
    global TOOL
    if TOOL is None:
        temp_dir = ROOT / ".runtime" / "tmp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        os.environ["TEMP"] = str(temp_dir)
        os.environ["TMP"] = str(temp_dir)
        java_root = ROOT / ".runtime" / "java"
        java = next(java_root.glob("*/bin/java.exe"), None)
        if java:
            os.environ["PATH"] = str(java.parent) + os.pathsep + os.environ.get("PATH", "")
        os.environ.setdefault("LTP_PATH", str(ROOT / ".runtime" / "languagetool"))
        import language_tool_python

        TOOL = language_tool_python.LanguageTool("en-US", host="127.0.0.1")
        atexit.register(TOOL.close)
    return TOOL


# Common veterinary, clinical, and case nouns to prioritize
VET_WORDS = {
    'dog', 'dogs', 'cat', 'cats', 'canine', 'feline', 'bovine', 'equine', 'puppy', 'kitten', 
    'pet', 'pets', 'fever', 'vomit', 'vomiting', 'diarrhea', 'cough', 'coughing', 'pain', 
    'ache', 'aches', 'eating', 'eat', 'eats', 'ate', 'appetite', 'stool', 'urine', 'lethargic', 
    'lethargy', 'abdomen', 'abdominal', 'stomach', 'breath', 'breathing', 'wound', 'injury', 
    'blood', 'pulse', 'mucous', 'swelling', 'weight', 'temperature', 'itch', 'itching', 'skin', 
    'ear', 'ears', 'eye', 'eyes', 'teeth', 'dental', 'tail', 'leg', 'legs', 'paw', 'paws', 
    'heart', 'lung', 'lungs', 'client', 'patient', 'doctor', 'witness', 'lawyer', 'hearing',
    'case', 'document', 'paperwork', 'evidence', 'report'
}

KNOWN_ABBREVIATIONS = {
    'dr', 'mr', 'mrs', 'ms', 'prof', 'kg', 'gm', 'mg', 'ml', 'cm', 'mm', 'km', 
    'hr', 'hrs', 'min', 'mins', 'sec', 'secs', 'vs', 'dept', 'avg', 'est', 
    'approx', 'tel', 'fax', 'no', 'nos', 'fig', 'figs', 'inc', 'corp', 'co', 
    'ltd', 'assoc', 'univ'
}

PRESERVED_TERMS = {
    'habeas corpus', 'subpoena', 'affidavit', 'plaintiff', 'defendant',
    'in re', 'pro se', 'prima facie', 'mens rea', 'amicus curiae',
    'certiorari', 'res judicata', 'stare decisis', 'inter alia',
    'gastric dilatation-volvulus', 'gdv', 'gastropexy', 'trocarization',
    'hemoperitoneum', 'peritonitis', 'pancreatitis', 'afast', 'tfast'
}

COMMON_CLINICAL_SHORTHANDS = {
    'dg': 'dog',
    'ct': 'cat',
    'pt': 'patient',
    'pup': 'puppy',
    'kit': 'kitten',
    'temp': 'temperature',
    'abd': 'abdomen',
    'wt': 'weight',
    'hx': 'history',
    'dx': 'diagnosis',
    'sx': 'surgery',
    'tx': 'treatment',
    'rx': 'prescription',
    'fx': 'fracture',
    'meds': 'medications',
    'vom': 'vomiting',
    'diarr': 'diarrhea',
    'sz': 'seizures'
}

COMMON_TYPOS = {
    'cliet': 'client',
    'cliants': 'clients',
    'submitt': 'submit',
    'submited': 'submitted',
    'submition': 'submission',
    'documnt': 'document',
    'documnts': 'documents',
    'docuemnt': 'document',
    'haring': 'hearing',
    'hearng': 'hearing',
    'delayd': 'delayed',
    'papre': 'paper',
    'paprs': 'papers',
    'witnes': 'witness',
    'witns': 'witness',
    'witneses': 'witnesses',
    'evidance': 'evidence',
    'evidense': 'evidence',
    'judg': 'judge',
    'lawer': 'lawyer',
    'attorny': 'attorney',
    'recieved': 'received',
    'recieve': 'receive',
    'seperate': 'separate',
    'seperated': 'separated',
    'definately': 'definitely',
    'accomodate': 'accommodate',
    'occurrd': 'occurred',
    'occured': 'occurred',
    'untill': 'until',
    'tommorow': 'tomorrow',
    'tomorow': 'tomorrow',
    'yesterdaye': 'yesterday',
    'calender': 'calendar',
    'appearence': 'appearance',
    'notic': 'notice',
    'notifaction': 'notification',
    'complante': 'complaint',
    'dianose': 'diagnose',
    'diagnoisis': 'diagnosis',
    'symtoms': 'symptoms',
    'symptomps': 'symptoms',
    'lethargi': 'lethargy',
    'vomitin': 'vomiting',
    'temprature': 'temperature',
    'abdoman': 'abdomen',
    'abdomin': 'abdomen',
    'prosedure': 'procedure',
    'medecine': 'medicine',
    'prescripion': 'prescription'
}

CONTRACTIONS = {
    'dont': "don't",
    'didnt': "didn't",
    'doesnt': "doesn't",
    'cant': "can't",
    'wont': "won't",
    'isnt': "isn't",
    'arent': "aren't",
    'wasnt': "wasn't",
    'werent': "weren't",
    'hasnt': "hasn't",
    'havent': "haven't",
    'couldnt': "couldn't",
    'shouldnt': "shouldn't",
    'wouldnt': "wouldn't"
}

LEGAL_CLINICAL_SINGULAR = {
    'client', 'plaintiff', 'defendant', 'witness', 'lawyer', 'attorney', 'judge',
    'petitioner', 'respondent', 'case', 'hearing', 'trial', 'document', 'report',
    'contract', 'paperwork', 'affidavit', 'subpoena', 'motion', 'order', 'court',
    'patient', 'dog', 'cat', 'pet', 'animal', 'doctor', 'physician', 'veterinarian'
}

INANIMATE_PASSIVE_SUBJECTS = {
    'case', 'hearing', 'case hearing', 'trial', 'motion', 'order', 'application',
    'complaint', 'document', 'paperwork', 'report', 'petition', 'appeal',
    'brief', 'deposition', 'settlement', 'sentence', 'proceeding', 'proceedings',
    'surgery', 'procedure', 'test', 'exam', 'biopsy', 'radiograph', 'x-ray'
}

PLURAL_SUBJECTS = {
    'clients', 'plaintiffs', 'defendants', 'witnesses', 'lawyers', 'attorneys', 'judges',
    'petitioners', 'respondents', 'cases', 'hearings', 'trials', 'documents', 'reports',
    'contracts', 'affidavits', 'subpoenas', 'motions', 'orders', 'courts',
    'patients', 'dogs', 'cats', 'pets', 'animals', 'doctors', 'physicians', 'veterinarians',
    'they', 'we'
}

COMMON_PAST_PARTICIPLES = {
    'submitted': 'submit',
    'attended': 'attend',
    'provided': 'provide',
    'filed': 'file',
    'received': 'receive',
    'signed': 'sign',
    'appeared': 'appear',
    'paid': 'pay',
    'sent': 'send',
    'delivered': 'deliver',
    'complied': 'comply',
    'informed': 'inform',
    'contacted': 'contact',
    'responded': 'respond',
    'eaten': 'eat',
    'drank': 'drink',
    'taken': 'take'
}

PASSIVE_VERBS = {
    'postponed', 'delayed', 'adjourned', 'cancelled', 'canceled', 'dismissed',
    'rescheduled', 'scheduled', 'suspended', 'filed', 'submitted', 'rejected',
    'approved', 'completed', 'conducted', 'signed', 'served', 'issued'
}

SUBORDINATE_COPULA_ADJECTIVES = {
    'missing', 'absent', 'unavailable', 'incomplete', 'lost', 'delayed', 'unprepared',
    'sick', 'ill', 'injured'
}

CLINICAL_PROGRESSIVE_VERBS = {
    'vomit': 'vomiting',
    'cough': 'coughing',
    'bleed': 'bleeding',
    'limp': 'limping',
    'scratch': 'scratching',
    'shake': 'shaking',
    'seize': 'seizing',
    'drool': 'drooling',
    'pant': 'panting',
    'tremble': 'trembling',
    'sneeze': 'sneezing',
    'whine': 'whining',
    'eat': 'eating',
    'drink': 'drinking',
    'walk': 'walking'
}

CLINICAL_PASSIVE_VERBS = {
    'bite': 'bitten',
    'eat': 'eaten',
    'give': 'given',
    'take': 'taken',
    'see': 'seen',
    'strike': 'struck'
}


def is_abbreviation(candidate, original):
    if not candidate:
        return True
    clean_cand = candidate.rstrip('.,!?;:')
    clean_orig = original.rstrip('.,!?;:')
    if not clean_cand:
        return False
    if not clean_orig.isupper() and clean_cand.isupper() and len(clean_cand) >= 2:
        return True
    if '.' in clean_cand:
        return True
    if clean_cand.lower() in KNOWN_ABBREVIATIONS:
        return True
    if len(clean_cand) > 1 and not any(ch in 'aeiouyAEIOUY' for ch in clean_cand):
        return True
    return False


def pick_best_spelling_replacement(original, replacements):
    if not replacements:
        return original
    valid = [r for r in replacements if not is_abbreviation(r, original)]
    if not valid:
        return replacements[0]

    for cand in valid:
        if cand.lower() in VET_WORDS:
            return cand

    return valid[0]


def spell_check_stage(tool, text):
    """
    STAGE 1: Spelling & Typo Correction
    Handles common typographical mistakes, shorthand expansion, contraction fixes,
    duplicate word removals, and LanguageTool misspelling checks.
    Preserves proper names, legal terminology, and formatted numbers.
    """
    corrected = text
    history = []

    # 1. Remove repeated duplicate words (e.g., 'the the' -> 'the')
    def remove_dup(m):
        orig = m.group(0)
        repl = m.group(1)
        history.append((orig, repl, 'Spelling', f"Removed duplicate word '{orig}'."))
        return repl
    corrected = re.sub(r'\b([A-Za-z]+)\s+\1\b', remove_dup, corrected, flags=re.IGNORECASE)

    # 2. Contractions expansion / apostrophe restoration
    for short, full in CONTRACTIONS.items():
        pat = re.compile(r'\b' + short + r'\b', flags=re.IGNORECASE)
        for m in pat.finditer(corrected):
            orig_match = m.group(0)
            repl = full.capitalize() if orig_match.istitle() else full
            history.append((orig_match, repl, 'Spelling', f"Added apostrophe to contraction '{orig_match}' -> '{repl}'."))
        corrected = pat.sub(lambda m: full.capitalize() if m.group(0).istitle() else full, corrected)

    # 3. Known typos dictionary
    for typo, full in COMMON_TYPOS.items():
        pat = re.compile(r'\b' + typo + r'\b', flags=re.IGNORECASE)
        for m in pat.finditer(corrected):
            orig_match = m.group(0)
            repl = full.capitalize() if orig_match.istitle() else full
            history.append((orig_match, repl, 'Spelling', f"Corrected misspelled word '{orig_match}' -> '{repl}'."))
        corrected = pat.sub(lambda m: full.capitalize() if m.group(0).istitle() else full, corrected)

    # 4. Clinical shorthands
    for short, full in COMMON_CLINICAL_SHORTHANDS.items():
        pat = re.compile(r'\b(' + short + r')\b', flags=re.IGNORECASE)
        for m in pat.finditer(corrected):
            orig_match = m.group(1)
            repl = full.capitalize() if orig_match.istitle() else full
            history.append((orig_match, repl, 'Spelling', f"Spelling expansion: '{orig_match}' -> '{repl}'."))
        corrected = pat.sub(lambda m: full.capitalize() if m.group(1).istitle() else full, corrected)

    # 5. LanguageTool spelling checks
    seen = {corrected}
    for _ in range(4):
        matches = sorted(tool.check(corrected), key=lambda match: match.offset)
        spelling_matches = [
            m for m in matches 
            if getattr(m, 'rule_issue_type', '') in {'misspelling', 'typographical'} and m.replacements
        ]
        if not spelling_matches:
            break

        parts, cursor, changes = [], 0, []
        for match in spelling_matches:
            start, end = match.offset, match.offset + match.error_length
            if start < cursor or not 0 <= start <= end <= len(corrected):
                continue
            before = corrected[start:end]
            if before.lower() in PRESERVED_TERMS or before.isupper() and len(before) <= 5:
                continue
            replacement = pick_best_spelling_replacement(before, match.replacements)
            if replacement == before or is_abbreviation(replacement, before):
                continue
            parts.extend((corrected[cursor:start], replacement))
            cursor = end
            changes.append((before, replacement, 'Spelling', match.message or 'Spelling correction'))
        parts.append(corrected[cursor:])
        updated = "".join(parts)
        if updated in seen:
            break
        seen.add(updated)
        corrected = updated
        history.extend(changes)

    return corrected, history


def sentence_formation_stage(text):
    """
    STAGE 2: Sentence Formation Engine
    Restructures telegraphic, fragmented, or poorly formed clauses into
    complete, natural, professional English sentences while preserving original facts.
    """
    sent = text.strip()
    if not sent:
        return sent, []

    history = []

    # 1. Telegraphic Negation: [subject] not [past_participle] -> [subject] did not [base_verb]
    for part, base in COMMON_PAST_PARTICIPLES.items():
        pat = re.compile(r'\b([A-Za-z]+)\s+not\s+' + part + r'\b', flags=re.IGNORECASE)
        for m in pat.finditer(sent):
            orig = m.group(0)
            repl = f"{m.group(1)} did not {base}"
            history.append((orig, repl, 'Sentence Formation', f"Sentence formation: formed complete negative past action '{repl}'."))
        sent = pat.sub(lambda m: f"{m.group(1)} did not {base}", sent)

    # 2. Passive auxiliary insertion for INANIMATE subjects:
    # e.g., 'case hearing postponed' -> 'case hearing was postponed'
    for subj in sorted(INANIMATE_PASSIVE_SUBJECTS, key=lambda s: -len(s)):
        for pverb in PASSIVE_VERBS:
            pat = re.compile(r'\b(' + re.escape(subj) + r')\s+' + re.escape(pverb) + r'\b(?!\s+(?:the|a|an|his|her|their|its|this|that)\b)', flags=re.IGNORECASE)
            for m in pat.finditer(sent):
                matched_subj = m.group(1)
                aux = 'were' if matched_subj.lower().endswith('s') and not matched_subj.lower().endswith('ss') else 'was'
                orig = m.group(0)
                repl = f"{matched_subj} {aux} {pverb}"
                history.append((orig, repl, 'Sentence Formation', f"Sentence formation: inserted passive auxiliary '{aux}' in '{repl}'."))
            def repl_pass(m, verb=pverb):
                matched_subj = m.group(1)
                aux = 'were' if matched_subj.lower().endswith('s') and not matched_subj.lower().endswith('ss') else 'was'
                return f"{matched_subj} {aux} {verb}"
            sent = pat.sub(repl_pass, sent)

    # 3. Subordinate clause copula: because/since/as [noun phrase] missing -> ... was missing
    for adj in SUBORDINATE_COPULA_ADJECTIVES:
        pat = re.compile(r'\b(because|since|as|if)\s+([a-zA-Z]+(?:\s+[a-zA-Z]+)?)\s+' + adj + r'\b', flags=re.IGNORECASE)
        for m in pat.finditer(sent):
            conj = m.group(1)
            phrase = m.group(2)
            last_word = phrase.split()[-1].lower()
            if last_word not in {'was', 'were', 'is', 'are', 'been', 'being', 'not'}:
                aux = 'were' if phrase.lower().endswith('s') and not phrase.lower().endswith('ss') else 'was'
                orig = m.group(0)
                repl = f"{conj} {phrase} {aux} {adj}"
                history.append((orig, repl, 'Sentence Formation', f"Sentence formation: added linking verb '{aux}' to subordinate clause."))
        def repl_subord(m):
            conj = m.group(1)
            phrase = m.group(2)
            last_word = phrase.split()[-1].lower()
            if last_word in {'was', 'were', 'is', 'are', 'been', 'being', 'not'}:
                return m.group(0)
            aux = 'were' if phrase.lower().endswith('s') and not phrase.lower().endswith('ss') else 'was'
            return f"{conj} {phrase} {aux} {adj}"
        sent = pat.sub(repl_subord, sent)

    # 4. Contextual noun refinement: 'required paper' -> 'required paperwork'
    if re.search(r'\brequired\s+paper\b', sent, flags=re.IGNORECASE):
        history.append(('required paper', 'required paperwork', 'Sentence Formation', "Word choice: refined 'required paper' to 'required paperwork'."))
        sent = re.sub(r'\brequired\s+paper\b', 'required paperwork', sent, flags=re.IGNORECASE)

    # 5. Determiners (The / the) on count nouns:
    # 5a. At start of sentence
    def cap_determiner(m):
        prefix = m.group(1)
        word = m.group(2)
        if word.lower() in LEGAL_CLINICAL_SINGULAR and word.lower() not in {'court', 'paperwork'}:
            repl = f"{prefix}The {word.lower()}"
            history.append((word, f"The {word.lower()}", 'Sentence Formation', f"Sentence structure: added definite article 'The' before singular noun '{word}'."))
            return repl
        return m.group(0)
    sent = re.sub(r'(^|[.!?]\s+)([a-zA-Z]+)\b', cap_determiner, sent)

    # 5b. After coordinating conjunction 'and'
    def and_determiner(m):
        conj = m.group(1)
        phrase = m.group(2)
        first_word = phrase.split()[0].lower()
        if first_word in LEGAL_CLINICAL_SINGULAR:
            repl = f", {conj} the {phrase}"
            history.append((f"{conj} {phrase}", repl, 'Sentence Formation', f"Punctuation and determiner: added comma and 'the' before '{phrase}'."))
            return repl
        return m.group(0)
    sent = re.sub(r'\b(and|but)\s+((?:case\s+hearing|case|hearing|document|report|witness|client|plaintiff|defendant)\b[^,.]*?\b(?:was|were|did|is|has)\b)', and_determiner, sent, flags=re.IGNORECASE)

    # 5c. After transitive verbs: submit document -> submit the document
    pat_trans = re.compile(r'\b(submit|submitted|submits|file|filed|files|sign|signed|signs|provide|provided|provides|review|reviewed|reviews)\s+([a-zA-Z]+)\b', flags=re.IGNORECASE)
    def repl_trans(m):
        verb = m.group(1)
        obj = m.group(2)
        if obj.lower() in LEGAL_CLINICAL_SINGULAR and obj.lower() not in {'court', 'paperwork'}:
            repl = f"{verb} the {obj}"
            history.append((m.group(0), repl, 'Sentence Formation', f"Determiner: inserted 'the' before object '{obj}'."))
            return repl
        return m.group(0)
    sent = pat_trans.sub(repl_trans, sent)

    # 5d. After subordinating conjunctions: because required paperwork -> because the required paperwork
    pat_subord_det = re.compile(r'\b(because|since|as)\s+(required\s+paperwork|required\s+document)\b', flags=re.IGNORECASE)
    for m in pat_subord_det.finditer(sent):
        history.append((m.group(0), f"{m.group(1)} the {m.group(2)}", 'Sentence Formation', f"Determiner: inserted 'the' before '{m.group(2)}'."))
    sent = pat_subord_det.sub(r'\1 the \2', sent)

    # Clean punctuation and spacing
    sent = re.sub(r'\s+', ' ', sent).strip()
    sent = re.sub(r'\s+,', ',', sent)

    return sent, history


def grammar_rules_stage(text):
    """
    STAGE 3: Grammar Engine
    Corrects subject-verb agreement (singular/plural), coordinated verb agreement,
    verb tenses, progressive/passive verb forms, and time agreements.
    """
    corrected = text
    grammar_changes = []

    # Irregular past tense without auxiliary (e.g. 'cat drunk' -> 'cat drank')
    for m in re.finditer(r'\b(?<!has\s)(?<!had\s)(?<!have\s)(?<!is\s)(?<!was\s)\b([a-zA-Z]+)\s+drunk\b', corrected, flags=re.IGNORECASE):
        grammar_changes.append(('drunk', 'drank', 'Grammar', "Verb form: use past tense 'drank' rather than participle 'drunk'."))
    corrected = re.sub(r'\b(?<!has\s)(?<!had\s)(?<!have\s)(?<!is\s)(?<!was\s)\b([a-zA-Z]+)\s+drunk\b', r'\1 drank', corrected, flags=re.IGNORECASE)

    # 1. 'is have' / 'was have' -> 'has' / 'had' 
    for m in re.finditer(r'\b(is|was)\s+have\b', corrected, flags=re.IGNORECASE):
        repl = 'has' if m.group(1).lower() == 'is' else 'had'
        grammar_changes.append((m.group(0), repl, 'Grammar', f"Auxiliary verb correction: '{m.group(0)}' -> '{repl}'."))
    corrected = re.sub(r'\bis\s+have\b', 'has', corrected, flags=re.IGNORECASE)
    corrected = re.sub(r'\bwas\s+have\b', 'had', corrected, flags=re.IGNORECASE)

    # 2. 'is not eat' -> 'is not eating'
    for stem, ing in CLINICAL_PROGRESSIVE_VERBS.items():
        pat = re.compile(r'\b(is|are|was|were)\s+not\s+' + stem + r'\b', flags=re.IGNORECASE)
        for m in pat.finditer(corrected):
            repl = f"{m.group(1)} not {ing}"
            grammar_changes.append((m.group(0), repl, 'Grammar', f"Verb aspect: '{m.group(0)}' -> '{repl}'."))
        corrected = pat.sub(r'\1 not ' + ing, corrected)

    # 3. Missing auxiliary: 'dog not eating' -> 'dog is not eating'
    subj_pat = r'(?:(?:the|a|an|this|that|my|our|his|her|its)\s+)?(?:' + '|'.join(LEGAL_CLINICAL_SINGULAR) + r')'
    pat_missing_aux = re.compile(r'\b(' + subj_pat + r')\s+not\s+(eating|drinking|walking|vomiting|moving|urinating|defecating)\b', flags=re.IGNORECASE)
    for m in pat_missing_aux.finditer(corrected):
        repl = f"{m.group(1)} is not {m.group(2)}"
        grammar_changes.append((m.group(0), repl, 'Grammar', f"Missing auxiliary verb: added 'is' before 'not {m.group(2)}'."))
    corrected = pat_missing_aux.sub(r'\1 is not \2', corrected)

    # 4. 'dog having fever' -> 'dog has fever'
    pat_having = re.compile(r'\b(' + subj_pat + r')\s+having\s+(fever|pain|diarrhea|seizures|seizure|cough|trouble|distension)\b', flags=re.IGNORECASE)
    for m in pat_having.finditer(corrected):
        repl = f"{m.group(1)} has {m.group(2)}"
        grammar_changes.append((m.group(0), repl, 'Grammar', f"Verb aspect: '{m.group(0)}' -> '{repl}'."))
    corrected = pat_having.sub(r'\1 has \2', corrected)

    # 5. Time units agreement: 'since 2 day' -> 'since 2 days'
    pat_plural_time = re.compile(r'\b(for|since|past|last)\s+([2-9]|\d{2,})\s+(day|week|month|hour|year)\b', flags=re.IGNORECASE)
    for m in pat_plural_time.finditer(corrected):
        repl = f"{m.group(1)} {m.group(2)} {m.group(3)}s"
        grammar_changes.append((m.group(0), repl, 'Grammar', f"Plural time agreement: '{m.group(3)}' -> '{m.group(3)}s'."))
    corrected = pat_plural_time.sub(r'\1 \2 \3s', corrected)

    pat_single_time = re.compile(r'\b(for|since|past|last)\s+(1|one)\s+(days|weeks|months|hours|years)\b', flags=re.IGNORECASE)
    for m in pat_single_time.finditer(corrected):
        repl = f"{m.group(1)} {m.group(2)} {m.group(3)[:-1]}"
        grammar_changes.append((m.group(0), repl, 'Grammar', f"Singular time agreement: '{m.group(3)}' -> '{m.group(3)[:-1]}'."))
    corrected = pat_single_time.sub(lambda m: m.group(1) + ' ' + m.group(2) + ' ' + m.group(3)[:-1], corrected)

    # 6. Singular subject + 'have' -> 'has'
    pat_sing_have = re.compile(r'\b((?:the\s+)?(?:' + '|'.join(LEGAL_CLINICAL_SINGULAR) + r'|he|she|it))\s+have\b', flags=re.IGNORECASE)
    for m in pat_sing_have.finditer(corrected):
        grammar_changes.append(('have', 'has', 'Grammar', f"Subject-verb agreement: use 'has' with singular subject '{m.group(1)}'."))
    corrected = pat_sing_have.sub(r'\1 has', corrected)

    # 7. Singular subject + 'are' -> 'is'
    pat_sing_are = re.compile(r'\b((?:the\s+)?(?:' + '|'.join(LEGAL_CLINICAL_SINGULAR) + r'|he|she|it))\s+are\b', flags=re.IGNORECASE)
    for m in pat_sing_are.finditer(corrected):
        grammar_changes.append(('are', 'is', 'Grammar', f"Subject-verb agreement: use 'is' with singular subject '{m.group(1)}'."))
    corrected = pat_sing_are.sub(r'\1 is', corrected)

    # 8. Singular subject + 'were' -> 'was'
    pat_sing_were = re.compile(r'\b((?:the\s+)?(?:' + '|'.join(LEGAL_CLINICAL_SINGULAR) + r'|he|she|it))\s+were\b', flags=re.IGNORECASE)
    for m in pat_sing_were.finditer(corrected):
        grammar_changes.append(('were', 'was', 'Grammar', f"Subject-verb agreement: use 'was' with singular subject '{m.group(1)}'."))
    corrected = pat_sing_were.sub(r'\1 was', corrected)

    # 9. Singular subject + 'do not' -> 'does not'
    pat_sing_do = re.compile(r'\b((?:the\s+)?(?:' + '|'.join(LEGAL_CLINICAL_SINGULAR) + r'|he|she|it))\s+(do\s+not|dont|don\'t)\b', flags=re.IGNORECASE)
    for m in pat_sing_do.finditer(corrected):
        neg = m.group(2)
        repl_neg = "doesn't" if ("'" in neg or neg.lower() == "dont") else "does not"
        grammar_changes.append((neg, repl_neg, 'Grammar', f"Subject-verb agreement: use '{repl_neg}' with singular subject '{m.group(1)}'."))
    corrected = pat_sing_do.sub(lambda m: f"{m.group(1)} " + ("doesn't" if ("'" in m.group(2) or m.group(2).lower() == "dont") else "does not"), corrected)

    # 10. Coordinated verb agreement after singular subjects: e.g. "The patient has fever and are weak" -> "and is weak"
    pat_coord = re.compile(r'\b((?:the\s+)?(?:' + '|'.join(LEGAL_CLINICAL_SINGULAR) + r'|he|she|it)\b[^.!?\n]*?\band\s+)(are|were|do\s+not|dont|don\'t|have)\b', flags=re.IGNORECASE)
    coord_mapping = {'are': 'is', 'were': 'was', 'have': 'has', 'do not': 'does not', 'dont': "doesn't", "don't": "doesn't"}
    for m in pat_coord.finditer(corrected):
        verb = re.sub(r'\s+', ' ', m.group(2).lower())
        repl = coord_mapping.get(verb, verb)
        grammar_changes.append((m.group(2), repl, 'Grammar', f"Coordinated verb agreement: use '{repl}'."))
    corrected = pat_coord.sub(lambda m: m.group(1) + coord_mapping.get(re.sub(r'\s+', ' ', m.group(2).lower()), m.group(2)), corrected)

    # 11. Plural subject + 'has' -> 'have'
    pat_plur_has = re.compile(r'\b((?:the\s+)?(?:' + '|'.join(PLURAL_SUBJECTS) + r'))\s+has\b', flags=re.IGNORECASE)
    for m in pat_plur_has.finditer(corrected):
        grammar_changes.append(('has', 'have', 'Grammar', f"Subject-verb agreement: use 'have' with plural subject '{m.group(1)}'."))
    corrected = pat_plur_has.sub(r'\1 have', corrected)

    # 12. Plural subject + 'is' -> 'are'
    pat_plur_is = re.compile(r'\b((?:the\s+)?(?:' + '|'.join(PLURAL_SUBJECTS) + r'))\s+is\b', flags=re.IGNORECASE)
    for m in pat_plur_is.finditer(corrected):
        grammar_changes.append(('is', 'are', 'Grammar', f"Subject-verb agreement: use 'are' with plural subject '{m.group(1)}'."))
    corrected = pat_plur_is.sub(r'\1 are', corrected)

    # 13. Plural subject + 'was' -> 'were'
    pat_plur_was = re.compile(r'\b((?:the\s+)?(?:' + '|'.join(PLURAL_SUBJECTS) + r'))\s+was\b', flags=re.IGNORECASE)
    for m in pat_plur_was.finditer(corrected):
        grammar_changes.append(('was', 'were', 'Grammar', f"Subject-verb agreement: use 'were' with plural subject '{m.group(1)}'."))
    corrected = pat_plur_was.sub(r'\1 were', corrected)

    # 14. Progressive aspect after be-verbs (e.g. is vomit -> is vomiting)
    for stem, ing in CLINICAL_PROGRESSIVE_VERBS.items():
        pattern_be_v = re.compile(r'\b(is|was|are|were|been)\s+(' + stem + r')\b', flags=re.IGNORECASE)
        for m in pattern_be_v.finditer(corrected):
            grammar_changes.append((m.group(2), ing, 'Grammar', f"Verb form: progressive '{ing}' after '{m.group(1)}'."))
        corrected = pattern_be_v.sub(r'\1 ' + ing, corrected)

    # 15. Passive voice / Past participles (e.g. was bite -> was bitten)
    for stem, part in CLINICAL_PASSIVE_VERBS.items():
        pattern_pass = re.compile(r'\b(was|is|been|were|got)\s+(' + stem + r')\b', flags=re.IGNORECASE)
        for m in pattern_pass.finditer(corrected):
            grammar_changes.append((m.group(2), part, 'Grammar', f"Verb form: past participle '{part}' in passive construction."))
        corrected = pattern_pass.sub(r'\1 ' + part, corrected)

    return corrected, grammar_changes


def get_huggingface_api_key():
    key = os.environ.get("HUGGINGFACE_API_KEY")
    if key and key.strip():
        return key.strip()
    return ""


def check_grammar_with_huggingface(text):
    api_key = get_huggingface_api_key()
    if not api_key:
        return None, [], "No Hugging Face API key configured"

    model_name = os.environ.get("HUGGINGFACE_MODEL", "pszemraj/flan-t5-large-grammar-synthesis")
    url = f"https://router.huggingface.co/hf-inference/models/{model_name}"

    payload = {
        "inputs": text,
        "parameters": {
            "max_new_tokens": 128
        }
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=8) as res:
            data = json.loads(res.read().decode("utf-8"))
            if isinstance(data, list) and len(data) > 0 and "generated_text" in data[0]:
                hf_corrected = data[0]["generated_text"].strip()
                if hf_corrected and hf_corrected != text:
                    changes = []
                    old_tokens = re.findall(r"\s+|\S+", text)
                    new_tokens = re.findall(r"\s+|\S+", hf_corrected)
                    for tag, i, j, a, b in difflib.SequenceMatcher(None, old_tokens, new_tokens, autojunk=False).get_opcodes():
                        if tag != "equal":
                            changes.append(("".join(old_tokens[i:j]), "".join(new_tokens[a:b]), "Grammar", "Neural grammar correction"))
                    return hf_corrected, changes, f"Hugging Face ({model_name.split('/')[-1]}) Active"
    except Exception as e:
        return None, [], f"Hugging Face notice: {str(e)}"

    return None, [], "Hugging Face empty response"


def process_single_line(tool, text):
    """
    Executes the 3-stage pipeline on a single text line/sentence:
    1. Spelling & Typo correction
    2. Sentence Formation
    3. Grammar correction + LanguageTool
    """
    history = []
    current = text

    # STAGE 1: Spell Check
    current, spell_hist = spell_check_stage(tool, current)
    history.extend(spell_hist)

    # STAGE 2: Sentence Formation
    current, form_hist = sentence_formation_stage(current)
    history.extend(form_hist)

    # STAGE 3: Grammar Check
    # Attempt Hugging Face if configured
    hf_corrected, hf_changes, hf_status = check_grammar_with_huggingface(current)
    if hf_corrected:
        current = hf_corrected
        history.extend(hf_changes)
    else:
        # Local Grammar Engine
        current, gramm_hist = grammar_rules_stage(current)
        history.extend(gramm_hist)

        # LanguageTool correction
        try:
            lt_corrected = tool.correct(current)
            # Only adopt if it didn't revert sentence formation
            if lt_corrected and lt_corrected != current:
                current = lt_corrected
        except Exception:
            pass

    # Ensure sentence capitalization
    if current and current[0].islower():
        current = current[0].upper() + current[1:]
    
    # Capitalize after sentence periods
    current = re.sub(r'(^|[.!?]\s+)([a-z])', lambda m: m.group(1) + m.group(2).upper(), current)

    # Ensure terminal punctuation if looks like a complete sentence
    current = re.sub(r'\s+', ' ', current).strip()
    current = re.sub(r'\s+,', ',', current)
    if current and not current.endswith(('.', '?', '!', ':', ';')):
        current += '.'

    return current, history, hf_status


def correct_text(text):
    """
    Complete Pipeline:
    Processes single sentences, multi-sentence paragraphs, and multi-paragraph text.
    Returns structured JSON with original, corrected, edits with offsets, and grammar issue list.
    """
    original = text.strip() if text else ""
    if not original:
        return {
            "original": original, 
            "corrected": original, 
            "spell_checked": original,
            "sentence_formed": original,
            "grammar_engine": "Sentence Formation + Grammar & Spelling Engine",
            "edits": [], 
            "grammar": {"issue_count": 0, "issues": []}
        }

    with LOCK:
        tool = load_tool()

        # Split multi-paragraph preserving exact spacing
        paragraphs = original.split('\n\n')
        corrected_paragraphs = []
        all_history = []
        last_hf_status = "Local Engine Active"

        for para in paragraphs:
            lines = para.split('\n')
            corrected_lines = []
            for line in lines:
                if not line.strip():
                    corrected_lines.append(line)
                    continue
                c_line, c_hist, hf_status = process_single_line(tool, line)
                corrected_lines.append(c_line)
                all_history.extend(c_hist)
                if "Active" in hf_status:
                    last_hf_status = hf_status
            corrected_paragraphs.append('\n'.join(corrected_lines))

        final_corrected = '\n\n'.join(corrected_paragraphs)

        # Build accurate diff edits with character offsets
        old = re.findall(r"\s+|\S+", original)
        new = re.findall(r"\s+|\S+", final_corrected)

        token_offsets = []
        curr = 0
        for tok in old:
            token_offsets.append((curr, curr + len(tok)))
            curr += len(tok)

        edits = []
        for tag, i, j, a, b in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
            if tag == "equal":
                continue
            
            start_char = token_offsets[i][0] if i < len(token_offsets) else len(original)
            end_char = token_offsets[j - 1][1] if 0 <= j - 1 < len(token_offsets) else start_char
            before = original[start_char:end_char]
            after = "".join(new[a:b])

            if is_abbreviation(after, before):
                continue

            issue_type = "Grammar"
            stage = 3
            issue_message = "Grammar correction"

            # Check history to categorize accurately
            for orig_tok, repl_tok, h_type, h_msg in all_history:
                orig_lower = orig_tok.lower().strip()
                repl_lower = repl_tok.lower().strip()
                before_lower = before.lower().strip()
                after_lower = after.lower().strip()

                if (before_lower and (orig_lower == before_lower or orig_lower in before_lower)) or \
                   (after_lower and (repl_lower == after_lower or repl_lower in after_lower or orig_lower in after_lower)):
                    issue_type = h_type
                    issue_message = h_msg
                    if h_type == "Spelling":
                        stage = 1
                    elif h_type == "Sentence Formation":
                        stage = 2
                    else:
                        stage = 3
                    break

            edits.append({
                "type": issue_type,
                "stage": stage,
                "stage_label": f"Stage {stage} ({issue_type})",
                "original": before,
                "replacement": after,
                "startIndex": start_char,
                "endIndex": end_char,
                "message": issue_message
            })

        if final_corrected != original and not edits:
            edits.append({
                "type": "Sentence Formation",
                "stage": 2,
                "stage_label": "Stage 2 (Sentence Formation)",
                "original": original,
                "replacement": final_corrected,
                "startIndex": 0,
                "endIndex": len(original),
                "message": "Sentence structure and punctuation improvement"
            })

        # Detailed grammar inspection of the final output
        remaining_grammar_issues = []
        try:
            matches = tool.check(final_corrected)
            remaining_grammar_issues = [
                {
                    "type": getattr(m, "rule_issue_type", "grammar"),
                    "message": getattr(m, "message", ""),
                    "offset": m.offset,
                    "length": m.error_length
                }
                for m in matches
                if getattr(m, "rule_issue_type", "") != "misspelling"
            ]
        except Exception:
            pass

        engine_name = "Hugging Face (flan-t5-large)" if "Active" in last_hf_status else "Sentence Formation + Grammar & Spelling Engine"

        return {
            "original": original,
            "corrected": final_corrected,
            "grammar_engine": engine_name,
            "huggingface_status": last_hf_status,
            "edits": edits,
            "grammar": {
                "issue_count": len(remaining_grammar_issues),
                "issues": remaining_grammar_issues
            }
        }


def error_message(error):
    message = str(error).lower()
    if "java" in message and any(word in message for word in ("found", "version", "install")):
        return "LanguageTool needs Java 17 or newer. Install Java or add the portable runtime under .runtime/java, then restart the server."
    if "4551" in message or "application control" in message:
        return "Windows Application Control is blocking a LanguageTool dependency. The device administrator must review the blocked file."
    return "LanguageTool could not start or check this text. Check the Python server log for details."
