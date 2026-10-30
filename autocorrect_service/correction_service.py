"""Local grammar and spelling correction using LanguageTool, without PyTorch."""


import atexit
import difflib
import os
import re
import threading
from pathlib import Path


ROOT = Path(__file__).resolve().parent
TOOL = None
LOCK = threading.Lock()



def load_tool():
    global TOOL
    if TOOL is None:
        # Java's local socket paths must fit Windows' path constraints. Keep
        # temporary files under the project rather than an inherited long path.
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



# Common veterinary and clinical words to prioritize for full word spelling resolution
VET_WORDS = {
    'dog', 'dogs', 'cat', 'cats', 'canine', 'feline', 'bovine', 'equine', 'puppy', 'kitten', 
    'pet', 'pets', 'fever', 'vomit', 'vomiting', 'diarrhea', 'cough', 'coughing', 'pain', 
    'ache', 'aches', 'eating', 'eat', 'eats', 'ate', 'appetite', 'stool', 'urine', 'lethargic', 
    'lethargy', 'abdomen', 'abdominal', 'stomach', 'breath', 'breathing', 'wound', 'injury', 
    'blood', 'pulse', 'mucous', 'swelling', 'weight', 'temperature', 'itch', 'itching', 'skin', 
    'ear', 'ears', 'eye', 'eyes', 'teeth', 'dental', 'tail', 'leg', 'legs', 'paw', 'paws', 
    'heart', 'lung', 'lungs'
}

# Known abbreviations, acronyms, and measurement units to disallow as spelling corrections
KNOWN_ABBREVIATIONS = {
    'dr', 'mr', 'mrs', 'ms', 'prof', 'kg', 'gm', 'mg', 'ml', 'cm', 'mm', 'km', 
    'hr', 'hrs', 'min', 'mins', 'sec', 'secs', 'vs', 'dept', 'avg', 'est', 
    'approx', 'tel', 'fax', 'no', 'nos', 'fig', 'figs', 'inc', 'corp', 'co', 
    'ltd', 'assoc', 'univ'
}


def is_abbreviation(candidate, original):
    """
    Detects whether a candidate is an abbreviation/acronym rather than a fully spelled-out word.
    """
    if not candidate:
        return True
    # Disallow all-uppercase acronyms (e.g. DG, SG, PR, MD, TV, USA) unless user originally typed uppercase
    if not original.isupper() and candidate.isupper() and len(candidate) >= 2:
        return True
    # Disallow dot abbreviations (e.g. Dr., etc., vs.)
    if '.' in candidate:
        return True
    # Disallow known abbreviations and unit codes
    if candidate.lower() in KNOWN_ABBREVIATIONS:
        return True
    # In English, real spelled-out words with length > 1 must contain at least one vowel
    if len(candidate) > 1 and not any(ch in 'aeiouyAEIOUY' for ch in candidate):
        return True
    return False


def pick_best_spelling_replacement(original, replacements):
    """
    Selects the best genuine, spelled-out word candidate, strictly eliminating abbreviations.
    """
    if not replacements:
        return original
    valid = [r for r in replacements if not is_abbreviation(r, original)]
    if not valid:
        return replacements[0]

    # Prioritize clinical/veterinary domain words (e.g., 'dg' -> 'dog' instead of 'do')
    for cand in valid:
        if cand.lower() in VET_WORDS:
            return cand

    # Otherwise return the highest-ranked non-abbreviation word
    return valid[0]


COMMON_CLINICAL_SHORTHANDS = {
    'dg': 'dog',
    'ct': 'cat',
    'pt': 'patient',
    'pup': 'puppy',
    'kit': 'kitten',
    'temp': 'temperature',
    'abd': 'abdomen'
}


def spell_check_stage(tool, text):
    """
    STAGE 1: Spell Check.
    Detects and corrects spelling errors in user input, resolving misspelled tokens to full words.
    """
    corrected, seen, history = text, {text}, []

    # Expand known clinical shorthands first
    for short, full in COMMON_CLINICAL_SHORTHANDS.items():
        pattern = re.compile(r'\b(' + short + r')\b', flags=re.IGNORECASE)
        for m in pattern.finditer(corrected):
            orig_match = m.group(1)
            repl = full.capitalize() if orig_match.istitle() else full
            history.append((orig_match, repl, 'Spelling', f"Spelling expansion: '{orig_match}' -> '{repl}'."))
        corrected = pattern.sub(lambda m: full.capitalize() if m.group(1).istitle() else full, corrected)

    for _ in range(6):
        matches = sorted(tool.check(corrected), key=lambda match: match.offset)
        spelling_matches = [
            m for m in matches 
            if getattr(m, 'rule_issue_type', '') == 'misspelling' and m.replacements
        ]
        if not spelling_matches:
            break

        parts, cursor, changes = [], 0, []
        for match in spelling_matches:
            start, end = match.offset, match.offset + match.error_length
            if start < cursor or not 0 <= start <= end <= len(corrected):
                continue
            before = corrected[start:end]
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


SINGULAR_CLINICAL_SUBJECTS = {
    'dog', 'cat', 'patient', 'puppy', 'kitten', 'pet', 'animal', 'canine', 'feline', 
    'bovine', 'equine', 'rabbit', 'bird', 'horse', 'cow', 'calf', 'heifer', 'lamb', 
    'sheep', 'goat', 'pig', 'piglet', 'hamster', 'ferret'
}

PLURAL_CLINICAL_SUBJECTS = {
    'dogs', 'cats', 'patients', 'puppies', 'kittens', 'pets', 'animals', 'canines', 
    'felines', 'rabbits', 'birds', 'horses', 'cows', 'calves', 'lambs', 
    'goats', 'pigs', 'hamsters', 'ferrets'
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
    'whine': 'whining'
}

CLINICAL_PASSIVE_VERBS = {
    'bite': 'bitten',
    'eat': 'eaten',
    'give': 'given',
    'take': 'taken',
    'see': 'seen',
    'strike': 'struck'
}


def enhance_clinical_grammar(text):
    """
    ENHANCED GRAMMAR ENGINE FOR CLINICAL COMPLAINT TEXT:
    Resolves subject-verb agreement (have/has, is/are, do/does not),
    progressive and passive verb forms, sentence capitalization, and punctuation.
    """
    corrected = text
    grammar_changes = []

    # 1. Singular subject + 'have' -> 'has'
    pattern_have = re.compile(
        r'\b((?:(?:the|a|an|this|that|my|our|his|her|its|one|each|every)\s+)?(?:[a-zA-Z-]+\s+)?'
        r'(?:' + '|'.join(SINGULAR_CLINICAL_SUBJECTS) + r'))\s+(have)\b',
        flags=re.IGNORECASE
    )
    for m in pattern_have.finditer(corrected):
        grammar_changes.append(('have', 'has', 'Grammar', f"Subject-verb agreement: use 'has' with singular '{m.group(1).strip()}'."))
    corrected = pattern_have.sub(r'\1 has', corrected)

    # 2. Singular subject + 'are' -> 'is'
    pattern_sing_are = re.compile(
        r'\b((?:(?:the|a|an|this|that|my|our|his|her|its|one|each|every)\s+)?(?:[a-zA-Z-]+\s+)?'
        r'(?:' + '|'.join(SINGULAR_CLINICAL_SUBJECTS) + r'))\s+(are)\b',
        flags=re.IGNORECASE
    )
    for m in pattern_sing_are.finditer(corrected):
        grammar_changes.append(('are', 'is', 'Grammar', f"Subject-verb agreement: use 'is' with singular subject '{m.group(1).strip()}'."))
    corrected = pattern_sing_are.sub(r'\1 is', corrected)

    # 3. Plural subject + 'is' -> 'are'
    pattern_plur_is = re.compile(
        r'\b((?:(?:the|these|those|my|our|his|her|its|both|all|several|two|three)\s+)?(?:[a-zA-Z-]+\s+)?'
        r'(?:' + '|'.join(PLURAL_CLINICAL_SUBJECTS) + r'))\s+(is)\b',
        flags=re.IGNORECASE
    )
    for m in pattern_plur_is.finditer(corrected):
        grammar_changes.append(('is', 'are', 'Grammar', f"Subject-verb agreement: use 'are' with plural subject '{m.group(1).strip()}'."))
    corrected = pattern_plur_is.sub(r'\1 are', corrected)

    # 4. Singular subject + 'do not' / 'dont' -> 'does not' / 'doesn't'
    pattern_do_not = re.compile(
        r'\b((?:(?:the|a|an|this|that|my|our|his|her|its|one|each|every)\s+)?(?:[a-zA-Z-]+\s+)?'
        r'(?:' + '|'.join(SINGULAR_CLINICAL_SUBJECTS) + r'))\s+(do\s+not|dont|don\'t)\b',
        flags=re.IGNORECASE
    )
    for m in pattern_do_not.finditer(corrected):
        neg = m.group(2)
        repl_neg = "doesn't" if ("'" in neg or neg.lower() == "dont") else "does not"
        grammar_changes.append((neg, repl_neg, 'Grammar', f"Subject-verb agreement: use '{repl_neg}' with singular subject '{m.group(1).strip()}'."))
    corrected = pattern_do_not.sub(
        lambda m: f"{m.group(1)} " + ("doesn't" if ("'" in m.group(2) or m.group(2).lower() == "dont") else "does not"), 
        corrected
    )

    # 5. Coordinated verb agreement after singular subjects (e.g. 'and do not' -> 'and does not', 'and are' -> 'and is')
    pattern_coord = re.compile(
        r'\b((?:' + '|'.join(SINGULAR_CLINICAL_SUBJECTS) + r')\b[^.!?\n]*?\band\s+)(are|were|do\s+not|dont|don\'t|have)\b',
        flags=re.IGNORECASE
    )
    coord_mapping = {
        'are': 'is',
        'were': 'was',
        'have': 'has',
        'do not': 'does not',
        'dont': "doesn't",
        "don't": "doesn't"
    }
    for m in pattern_coord.finditer(corrected):
        verb = re.sub(r'\s+', ' ', m.group(2).lower())
        repl = coord_mapping.get(verb, verb)
        grammar_changes.append((m.group(2), repl, 'Grammar', f"Coordinated verb agreement: use '{repl}'."))
    corrected = pattern_coord.sub(
        lambda m: m.group(1) + coord_mapping.get(re.sub(r'\s+', ' ', m.group(2).lower()), m.group(2)), 
        corrected
    )

    # 6. Progressive aspect after be-verbs (e.g. is vomit -> is vomiting)
    for stem, ing in CLINICAL_PROGRESSIVE_VERBS.items():
        pattern_be_v = re.compile(r'\b(is|was|are|were|been)\s+(' + stem + r')\b', flags=re.IGNORECASE)
        for m in pattern_be_v.finditer(corrected):
            grammar_changes.append((m.group(2), ing, 'Grammar', f"Verb form: use progressive form '{ing}' after '{m.group(1)}'."))
        corrected = pattern_be_v.sub(r'\1 ' + ing, corrected)

    # 7. Passive voice / Past participles (e.g. was bite -> was bitten)
    for stem, part in CLINICAL_PASSIVE_VERBS.items():
        pattern_pass = re.compile(r'\b(was|is|been|were|got)\s+(' + stem + r')\b', flags=re.IGNORECASE)
        for m in pattern_pass.finditer(corrected):
            grammar_changes.append((m.group(2), part, 'Grammar', f"Verb form: use past participle '{part}' in passive construction."))
        corrected = pattern_pass.sub(r'\1 ' + part, corrected)

    # 8. Sentence-start capitalization (e.g. 'the dog is sick' -> 'The dog is sick')
    def cap_sent(m):
        return m.group(1) + m.group(2).upper()
    corrected = re.sub(r'(^|[.!?]\s+)([a-z])', cap_sent, corrected)

    return corrected, grammar_changes


def grammar_check_stage(tool, text):
    """
    STAGE 2: Grammar Check.
    Applied to the text AFTER spelling has been checked and corrected.
    Combines clinical grammar enhancement with LanguageTool syntactic parsing.
    """
    # 2A. Enhanced Clinical Grammar Rules
    enhanced_text, enhanced_changes = enhance_clinical_grammar(text)

    # 2B. LanguageTool syntactic rules
    corrected, seen, history = enhanced_text, {enhanced_text}, list(enhanced_changes)
    for _ in range(6):
        matches = sorted(tool.check(corrected), key=lambda match: match.offset)
        # Select grammar, syntax, and agreement rules (non-misspelling)
        grammar_matches = [
            m for m in matches 
            if getattr(m, 'rule_issue_type', '') != 'misspelling' and m.replacements
        ]
        if not grammar_matches:
            break

        selected, grammar_sentences = [], set()
        for match in reversed(grammar_matches):
            sentence = len(re.findall(r"[.!?\n]", corrected[:match.offset]))
            if sentence in grammar_sentences:
                continue
            grammar_sentences.add(sentence)
            selected.append(match)

        parts, cursor, changes = [], 0, []
        for match in sorted(selected, key=lambda item: item.offset):
            start, end = match.offset, match.offset + match.error_length
            if start < cursor or not 0 <= start <= end <= len(corrected):
                continue
            before = corrected[start:end]
            replacement = match.replacements[0]
            if replacement == before:
                continue
            parts.extend((corrected[cursor:start], replacement))
            cursor = end
            changes.append((before, replacement, 'Grammar', match.message or 'Grammar correction'))
        parts.append(corrected[cursor:])
        updated = "".join(parts)
        if updated in seen:
            break
        seen.add(updated)
        corrected = updated
        history.extend(changes)
    return corrected, history


def check_grammar(text):
    """
    Checks the supplied text for grammar, spelling, punctuation, and style issues.

    Returns:
        dict: Original text, issue count, detailed issues, and corrected text.
    """
    original = text.strip()

    if not original:
        return {
            "text": original,
            "issue_count": 0,
            "issues": [],
            "corrected": original,
        }

    with LOCK:
        tool = load_tool()
        matches = tool.check(original)
        corrected = tool.correct(original)

    issues = []

    for match in matches:
        start = match.offset
        end = match.offset + match.error_length

        issues.append(
            {
                "type": getattr(match, "rule_issue_type", None) or "grammar",
                "rule_id": getattr(match, "ruleId", ""),
                "message": getattr(match, "message", ""),
                "original": original[start:end],
                "suggestions": list(getattr(match, "replacements", []) or []),
                "offset": start,
                "length": match.error_length,
                "context": getattr(match, "context", "").strip(),
            }
        )

    return {
        "text": original,
        "issue_count": len(issues),
        "issues": issues,
        "corrected": corrected,
    }


def correct_text(text):
    """
    Two-step pipeline:
    Step 1: Apply Spell Check to user input to fix misspellings to full words.
    Step 2: Apply Grammar Check to the spell-checked text to fix subject-verb agreement and syntax.
    """
    original = text.strip()
    if not original:
        return {"original": original, "corrected": original, "edits": [], "grammar": {"issue_count": 0, "issues": []}}

    with LOCK:
        tool = load_tool()

        # STEP 1: Apply spell check to the raw user input
        after_spell_check, spell_history = spell_check_stage(tool, original)

        # STEP 2: Apply grammar check to the spell-checked text
        after_grammar_check, grammar_history = grammar_check_stage(tool, after_spell_check)

        final_corrected = after_grammar_check
        all_history = spell_history + grammar_history

        # Build clean, accurate edits mapping original input to final corrected output
        old, new = re.findall(r"\s+|\S+", original), re.findall(r"\s+|\S+", final_corrected)
        edits = []
        for tag, i, j, a, b in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
            if tag == "equal":
                continue
            before, after = "".join(old[i:j]), "".join(new[a:b])
            if is_abbreviation(after, before):
                continue

            # Determine whether this change was introduced by the spell check or grammar check stage
            issue_type = "Grammar"
            issue_message = "Review this suggested change."
            for orig_tok, repl_tok, h_type, h_msg in all_history:
                if orig_tok in before:
                    issue_type = h_type
                    issue_message = h_msg
                    break

            edits.append({
                "type": issue_type,
                "original": before,
                "replacement": after,
                "message": issue_message
            })

        # Detailed grammar inspection of the final output
        remaining_grammar_issues = [
            {
                "type": getattr(m, "rule_issue_type", "grammar"),
                "message": getattr(m, "message", ""),
                "offset": m.offset,
                "length": m.error_length
            }
            for m in tool.check(final_corrected)
            if getattr(m, "rule_issue_type", "") != "misspelling"
        ]

        return {
            "original": original,
            "corrected": final_corrected,
            "spell_checked": after_spell_check,
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
    return "LanguageTool could not start or check this text. First use downloads its local language files. Check the Python server log for the specific error."