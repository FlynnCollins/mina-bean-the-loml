#!/usr/bin/env python
"""
Splunk Custom Fuzzy Matching Streaming Command
Implements flexible fuzzy string matching using rapidfuzz library

Installation:
  - Install rapidfuzz: pip install rapidfuzz
  - Place this file in: $SPLUNK_HOME/etc/apps/fuzzy_match/bin/fuzzymatch.py
  - Create commands.conf entry in $SPLUNK_HOME/etc/apps/fuzzy_match/default/
"""

import sys
import logging
from abc import ABC, abstractmethod
from typing import Callable, Dict, List, Optional, Tuple

try:
    from splunklib.searchcommands import (
        StreamingCommand,
        Configuration,
        Option,
        validators,
    )

    HAS_SPLUNK = True
except ImportError:
    HAS_SPLUNK = False

try:
    from rapidfuzz import fuzz, process
    from rapidfuzz.distance import Levenshtein

    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False


# ============================================================================
# Text Processors
# ============================================================================


class TextProcessor(ABC):
    """Base class for text preprocessing strategies"""

    @abstractmethod
    def process(self, text: str) -> str:
        """Process/normalize text"""
        pass


class NoProcessor(TextProcessor):
    """No preprocessing"""

    def process(self, text: str) -> str:
        return text


class DefaultProcessor(TextProcessor):
    """Lowercase + strip whitespace (standard preprocessing)"""

    def process(self, text: str) -> str:
        if not isinstance(text, str):
            return ""
        return text.lower().strip()


class TrimProcessor(TextProcessor):
    """Strip leading/trailing whitespace only"""

    def process(self, text: str) -> str:
        if not isinstance(text, str):
            return ""
        return text.strip()


class LowercaseProcessor(TextProcessor):
    """Lowercase conversion only"""

    def process(self, text: str) -> str:
        if not isinstance(text, str):
            return ""
        return text.lower()


class AlphanumericProcessor(TextProcessor):
    """Keep only alphanumeric characters, lowercase"""

    def process(self, text: str) -> str:
        if not isinstance(text, str):
            return ""
        return "".join(c for c in text.lower() if c.isalnum())


class NoPunctuationProcessor(TextProcessor):
    """Remove punctuation, keep alphanumeric and spaces"""

    def process(self, text: str) -> str:
        if not isinstance(text, str):
            return ""
        return "".join(c for c in text if c.isalnum() or c.isspace()).lower()


PROCESSORS: Dict[str, TextProcessor] = {
    "none": NoProcessor(),
    "default": DefaultProcessor(),
    "trim": TrimProcessor(),
    "lowercase": LowercaseProcessor(),
    "alphanumeric": AlphanumericProcessor(),
    "no_punct": NoPunctuationProcessor(),
}


# ============================================================================
# Fuzzy Matching Algorithms
# ============================================================================


class FuzzyMatcher(ABC):
    """Base class for fuzzy matching algorithms"""

    def __init__(self, processor: TextProcessor, case_sensitive: bool = False):
        self.processor = processor
        self.case_sensitive = case_sensitive

    @abstractmethod
    def score(self, s1: str, s2: str) -> float:
        """Return match score 0-100"""
        pass

    def _preprocess(self, text: str) -> str:
        """Apply preprocessing unless case_sensitive"""
        if self.case_sensitive or not isinstance(self.processor, DefaultProcessor):
            return self.processor.process(text)
        if not isinstance(text, str):
            return ""
        return text.lower().strip()


class ExactMatcher(FuzzyMatcher):
    """Exact string matching"""

    def score(self, s1: str, s2: str) -> float:
        p1 = self._preprocess(s1)
        p2 = self._preprocess(s2)
        return 100.0 if p1 == p2 else 0.0


class SimpleRatioMatcher(FuzzyMatcher):
    """Basic fuzzy matching using simple ratio"""

    def score(self, s1: str, s2: str) -> float:
        p1 = self._preprocess(s1)
        p2 = self._preprocess(s2)
        return float(fuzz.ratio(p1, p2))


class TokenSetMatcher(FuzzyMatcher):
    """Token-based matching (order-independent)"""

    def score(self, s1: str, s2: str) -> float:
        p1 = self._preprocess(s1)
        p2 = self._preprocess(s2)
        return float(fuzz.token_set_ratio(p1, p2))


class TokenSortMatcher(FuzzyMatcher):
    """Sort tokens before matching"""

    def score(self, s1: str, s2: str) -> float:
        p1 = self._preprocess(s1)
        p2 = self._preprocess(s2)
        return float(fuzz.token_sort_ratio(p1, p2))


class PartialRatioMatcher(FuzzyMatcher):
    """Partial string matching (best substring match)"""

    def score(self, s1: str, s2: str) -> float:
        p1 = self._preprocess(s1)
        p2 = self._preprocess(s2)
        return float(fuzz.partial_ratio(p1, p2))


class DistanceMatcher(FuzzyMatcher):
    """Levenshtein edit distance converted to similarity score"""

    def score(self, s1: str, s2: str) -> float:
        p1 = self._preprocess(s1)
        p2 = self._preprocess(s2)
        max_len = max(len(p1), len(p2))
        if max_len == 0:
            return 100.0
        distance = Levenshtein.distance(p1, p2)
        # Convert distance to similarity (100 = identical, 0 = completely different)
        return max(0, 100.0 * (1.0 - distance / max_len))


class JaroWinklerMatcher(FuzzyMatcher):
    """Jaro-Winkler similarity (optimized for short strings)"""

    def score(self, s1: str, s2: str) -> float:
        p1 = self._preprocess(s1)
        p2 = self._preprocess(s2)
        return float(fuzz.QRatio(p1, p2))


# Algorithm registry
ALGORITHM_MATCHERS: Dict[str, type] = {
    "exact": ExactMatcher,
    "simple_ratio": SimpleRatioMatcher,
    "token_set": TokenSetMatcher,
    "token_sort": TokenSortMatcher,
    "partial_ratio": PartialRatioMatcher,
    "distance": DistanceMatcher,
    "jaro_winkler": JaroWinklerMatcher,
}

ALGORITHM_DESCRIPTIONS = {
    "exact": "Exact string matching",
    "simple_ratio": "Basic fuzzy matching",
    "token_set": "Token-based matching (order-independent) [DEFAULT]",
    "token_sort": "Sort tokens before matching",
    "partial_ratio": "Partial string matching (best substring match)",
    "distance": "Levenshtein edit distance",
    "jaro_winkler": "Jaro-Winkler similarity (optimized for names)",
}


# ============================================================================
# Splunk Streaming Command
# ============================================================================


@Configuration()
class FuzzyMatchCommand(StreamingCommand):
    """
    Custom streaming command for fuzzy string matching using rapidfuzz

    Syntax:
        | fuzzymatch field=<field> [match_field=<field> | choices=<list> | choices_from_field=<field>]
                    [algorithm=<algo>] [threshold=<score>] [processor=<processor>]
                    [output_field=<field>] [output_score=<field>]
                    [case_sensitive=<bool>]

    Examples:
        | fuzzymatch field=user_input match_field=product_name algorithm=jaro_winkler threshold=85
        | fuzzymatch field=value choices="cat,dog,bird" algorithm=partial_ratio threshold=75
        | fuzzymatch field=address match_field=ref_address algorithm=token_set processor=alphanumeric
    """

    # Core required arguments
    field = Option(require=True, help="The field containing the string to match")

    # Match source (choose one)
    match_field = Option(
        require=False, help="The field to match against (for record-to-record matching)"
    )
    choices = Option(
        require=False, help="Comma-separated static list of match candidates"
    )
    choices_from_field = Option(
        require=False,
        help="Field name containing semi-colon or comma-separated candidates",
    )

    # Algorithm and scoring
    algorithm = Option(
        default="token_set",
        validate=validators.Set(
            "exact",
            "simple_ratio",
            "token_set",
            "token_sort",
            "partial_ratio",
            "distance",
            "jaro_winkler",
        ),
        help="Matching algorithm (default: token_set)",
    )

    threshold = Option(
        default="80",
        validate=validators.Regex(r"^[0-9.]+$"),
        help="Minimum match score 0-100 (default: 80)",
    )

    processor = Option(
        default="default",
        validate=validators.Set(
            "none", "default", "trim", "lowercase", "alphanumeric", "no_punct"
        ),
        help="Text preprocessing strategy (default: default)",
    )

    # Output
    output_field = Option(
        default="fuzzy_match",
        help="Field name for matched result (default: fuzzy_match)",
    )

    output_score = Option(
        default="fuzzy_score", help="Field name for match score (default: fuzzy_score)"
    )

    # Options
    case_sensitive = Option(
        default="false",
        validate=validators.Boolean(),
        help="Preserve case in matching (default: false)",
    )

    def validate_arguments(self) -> None:
        """Validate argument combinations"""
        # Must specify match source
        match_sources = sum(
            [bool(self.match_field), bool(self.choices), bool(self.choices_from_field)]
        )

        if match_sources == 0:
            raise ValueError(
                "Must specify ONE of: match_field, choices, or choices_from_field"
            )

        if match_sources > 1:
            raise ValueError(
                "Can only specify ONE of: match_field, choices, or choices_from_field"
            )

        # Validate threshold
        try:
            threshold_val = float(self.threshold)
            if not (0 <= threshold_val <= 100):
                raise ValueError()
        except (ValueError, TypeError):
            raise ValueError(
                f"threshold must be a number between 0 and 100, got: {self.threshold}"
            )

    def stream(self, records):
        """Process each record with fuzzy matching"""
        try:
            self.validate_arguments()
        except ValueError as e:
            self.write_error(f"Argument validation error: {e}")
            return

        # Initialize matcher and processor
        try:
            processor = PROCESSORS[self.processor]
            matcher_class = ALGORITHM_MATCHERS[self.algorithm]
            is_case_sensitive = self.case_sensitive.lower() in ("true", "1", "yes")
            matcher = matcher_class(processor, case_sensitive=is_case_sensitive)
            threshold_val = float(self.threshold)
        except (KeyError, ValueError) as e:
            self.write_error(f"Error initializing matcher: {e}")
            return

        # Parse choices if static list
        static_choices = None
        if self.choices:
            static_choices = [c.strip() for c in self.choices.split(",")]

        # Process records
        for record in records:
            try:
                input_value = record.get(self.field, "")

                if not input_value:
                    record[self.output_field] = ""
                    record[self.output_score] = "0"
                    yield record
                    continue

                # Get match candidates
                candidates = self._get_candidates(record, static_choices)

                if not candidates:
                    record[self.output_field] = ""
                    record[self.output_score] = "0"
                    yield record
                    continue

                # Find best match
                if self.match_field and len(candidates) == 1:
                    # Single field matching
                    score = matcher.score(input_value, candidates[0])
                    record[self.output_field] = (
                        candidates[0] if score >= threshold_val else ""
                    )
                    record[self.output_score] = f"{score:.2f}"
                else:
                    # Multiple candidates - find best
                    best_match = ""
                    best_score = 0.0

                    for candidate in candidates:
                        score = matcher.score(input_value, candidate)
                        if score > best_score:
                            best_score = score
                            best_match = candidate

                    record[self.output_field] = (
                        best_match if best_score >= threshold_val else ""
                    )
                    record[self.output_score] = f"{best_score:.2f}"

                yield record

            except Exception as e:
                self.logger.error(f"Error processing record: {e}")
                record[self.output_field] = ""
                record[self.output_score] = "0"
                yield record

    def _get_candidates(
        self, record: dict, static_choices: Optional[List[str]]
    ) -> List[str]:
        """Extract match candidates from record or static list"""
        if static_choices:
            return static_choices

        if self.match_field:
            value = record.get(self.match_field, "")
            return [value] if value else []

        if self.choices_from_field:
            value = record.get(self.choices_from_field, "")
            if not value:
                return []
            # Support both semicolon and comma separation
            separator = ";" if ";" in value else ","
            return [c.strip() for c in value.split(separator) if c.strip()]

        return []


# ============================================================================
# Testing and Standalone Usage
# ============================================================================

if __name__ == "__main__":
    """Quick test/demo of the fuzzy matcher"""

    if not HAS_RAPIDFUZZ:
        print("ERROR: rapidfuzz library not installed")
        print("Install with: pip install rapidfuzz")
        sys.exit(1)

    # Test data
    test_cases = [
        ("john smith", "jon smith", "token_set", 80),
        ("john smith", "smith john", "token_set", 80),
        ("New York, NY", "new york ny", "token_set", 85),
        ("cat", ["cat", "dog", "bird", "cats"], "simple_ratio", 70),
        ("hello", "helo", "distance", 80),
        ("john", "jon", "jaro_winkler", 85),
    ]

    print("=" * 70)
    print("FUZZY MATCH TESTING")
    print("=" * 70)

    for test_case in test_cases:
        if len(test_case) == 4 and isinstance(test_case[1], list):
            input_str, candidates, algo, threshold = test_case
            processor = PROCESSORS["default"]
            matcher_class = ALGORITHM_MATCHERS[algo]
            matcher = matcher_class(processor, case_sensitive=False)

            best_match = ""
            best_score = 0.0
            for candidate in candidates:
                score = matcher.score(input_str, candidate)
                if score > best_score:
                    best_score = score
                    best_match = candidate

            status = "✓ MATCH" if best_score >= threshold else "✗ NO MATCH"
            print(f"\n{status}")
            print(f"  Input:    '{input_str}'")
            print(f"  Candidates: {candidates}")
            print(f"  Algorithm: {algo}")
            print(f"  Best match: '{best_match}' (score: {best_score:.1f})")
            print(f"  Threshold: {threshold}")
        else:
            input_str, match_str, algo, threshold = test_case
            processor = PROCESSORS["default"]
            matcher_class = ALGORITHM_MATCHERS[algo]
            matcher = matcher_class(processor, case_sensitive=False)
            score = matcher.score(input_str, match_str)

            status = "✓ MATCH" if score >= threshold else "✗ NO MATCH"
            print(f"\n{status}")
            print(f"  Input:      '{input_str}'")
            print(f"  Compare:    '{match_str}'")
            print(f"  Algorithm:  {algo}")
            print(f"  Score:      {score:.1f}")
            print(f"  Threshold:  {threshold}")

    print("\n" + "=" * 70)
    print("Available Algorithms:")
    print("=" * 70)
    for algo, desc in ALGORITHM_DESCRIPTIONS.items():
        print(f"  {algo:20} - {desc}")

    print("\nAvailable Processors:")
    print("=" * 70)
    processors_info = {
        "none": "No preprocessing",
        "default": "Lowercase + strip whitespace",
        "trim": "Strip leading/trailing whitespace",
        "lowercase": "Lowercase only",
        "alphanumeric": "Keep only alphanumeric + lowercase",
        "no_punct": "Remove punctuation + lowercase",
    }
    for proc, desc in processors_info.items():
        print(f"  {proc:20} - {desc}")
