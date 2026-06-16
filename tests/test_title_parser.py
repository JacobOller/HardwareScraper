import pytest
from hardware_scraper.parsers.title_parser import TitleParser


@pytest.fixture
def parser():
    return TitleParser()


class TestCategoryDetection:
    def test_rtx_gpu(self, parser):
        r = parser.parse("RTX 3070 Ti 8GB Gaming GPU")
        assert r.category == "gpu"

    def test_rx_gpu(self, parser):
        r = parser.parse("AMD RX 6800 XT Graphics Card")
        assert r.category == "gpu"

    def test_intel_cpu(self, parser):
        r = parser.parse("Intel Core i7-12700K processor")
        assert r.category == "cpu"

    def test_ryzen_cpu(self, parser):
        r = parser.parse("Ryzen 9 5900X AM4 CPU")
        assert r.category == "cpu"

    def test_ram(self, parser):
        r = parser.parse("32GB DDR4 3200MHz RAM")
        assert r.category == "ram"

    def test_unknown(self, parser):
        r = parser.parse("random item for sale")
        assert r.category is None


class TestModelExtraction:
    def test_rtx_model(self, parser):
        r = parser.parse("EVGA RTX 3080 10GB XC3 GAMING")
        assert r.model is not None
        assert "3080" in r.model

    def test_ryzen_model(self, parser):
        r = parser.parse("Ryzen 7 5800X boxed")
        assert r.model is not None
        assert "5800X" in r.model

    def test_i9_model(self, parser):
        r = parser.parse("Intel Core i9-12900K")
        assert r.model is not None
        assert "12900K" in r.model


class TestConditionDetection:
    def test_for_parts(self, parser):
        r = parser.parse("GTX 1080 for parts not working")
        assert r.condition == "for_parts"

    def test_like_new(self, parser):
        r = parser.parse("RTX 3090 like new barely used")
        assert r.condition == "like_new"

    def test_default_used(self, parser):
        r = parser.parse("RTX 3070 used great condition")
        assert r.condition == "used"


class TestConfidenceScore:
    def test_full_confidence(self, parser):
        r = parser.parse("NVIDIA RTX 3070 Ti 8GB like new")
        assert r.confidence >= 0.9

    def test_partial_confidence(self, parser):
        r = parser.parse("graphics card for sale")
        assert r.confidence < 0.6

    def test_no_match_low_confidence(self, parser):
        r = parser.parse("selling my stuff")
        assert r.confidence == 0.0


class TestCanonicalName:
    def test_gpu_canonical(self, parser):
        r = parser.parse("NVIDIA RTX 3080 10GB GPU")
        assert r.canonical_name is not None
        assert "RTX" in r.canonical_name
        assert "3080" in r.canonical_name

    def test_no_canonical_without_model(self, parser):
        r = parser.parse("GPU for sale")
        assert r.canonical_name is None
