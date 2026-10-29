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


def pick_best_replacement(original, replacements):
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


def _autocorrect_single_stage(tool, text):
    """Executes a full iterative autocorrection stage resolving conflicting rules without abbreviations."""
    corrected, seen, history = text, {text}, []
    for _ in range(8):
        matches = sorted(tool.check(corrected), key=lambda match: match.offset)
        selected, grammar_sentences = [], set()
        for match in reversed(matches):
            if not match.replacements:
                continue
            if getattr(match, "rule_issue_type", "") != "misspelling":
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
            replacement = pick_best_replacement(before, match.replacements)
            if replacement == before or is_abbreviation(replacement, before):
                continue
            parts.extend((corrected[cursor:start], replacement))
            cursor = end
            changes.append((before, replacement, getattr(match, "rule_issue_type", "grammar"), getattr(match, "message", "")))
        parts.append(corrected[cursor:])
        updated = "".join(parts)
        if updated in seen:
            break
        seen.add(updated)
        corrected = updated
        history.extend(changes)
    return corrected, history


def correct_text(text):
    """
    Two-stage cascaded autocorrection:
    Stage 1: Autocorrects initial user input for spelling errors, strictly avoiding abbreviations.
    Stage 2: The output of Stage 1 again undergoes autocorrection to ensure that
             fixing spelling has not introduced or revealed secondary grammatical issues.
    """
    original = text.strip()
    with LOCK:
        tool = load_tool()

        # Pass 1: Autocorrect the user input (spelling only, fully spelled-out words)
        first_pass_output, history_pass1 = _autocorrect_single_stage(tool, original)

        # Pass 2: The output again undergoes full autocorrection
        second_pass_output, history_pass2 = _autocorrect_single_stage(tool, first_pass_output)

        final_corrected = second_pass_output

        history = history_pass1 + history_pass2

        # Show differences between the original and final corrected text, excluding abbreviations
        old, new = re.findall(r"\s+|\S+", original), re.findall(r"\s+|\S+", final_corrected)
        edits = []
        for tag, i, j, a, b in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
            if tag == "equal":
                continue
            before, after = "".join(old[i:j]), "".join(new[a:b])
            # Never suggest an abbreviation as a replacement
            if is_abbreviation(after, before):
                continue
            spelling = any(kind == "misspelling" and src in before and dst in after for src, dst, kind, _ in history)
            edits.append({"type": "Spelling" if spelling else "Grammar", "original": before,
                          "replacement": after, "message": "Review this suggested change."})
        return {"original": original, "corrected": final_corrected, "edits": edits}


def error_message(error):
    message = str(error).lower()
    if "java" in message and any(word in message for word in ("found", "version", "install")):
        return "LanguageTool needs Java 17 or newer. Install Java or add the portable runtime under .runtime/java, then restart the server."
    if "4551" in message or "application control" in message:
        return "Windows Application Control is blocking a LanguageTool dependency. The device administrator must review the blocked file."
    return "LanguageTool could not start or check this text. First use downloads its local language files. Check the Python server log for the specific error."
