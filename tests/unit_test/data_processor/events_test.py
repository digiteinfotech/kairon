from kairon.shared.augmentation.utils import AugmentationUtils


class TestSimilarity:

    def test_similarity(self):
        sentences = ["i love you", "good boy"]
        assert AugmentationUtils.get_similar(sentences, "i love you", 0.70)
