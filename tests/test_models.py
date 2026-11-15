import unittest

import torch

from eeg_emostudio.models.registry import build_model


class ModelTests(unittest.TestCase):
    def setUp(self):
        torch.manual_seed(0)

    def test_feature_models_forward(self):
        for name in ["mlp", "dgcnn", "dualview"]:
            model = build_model(name, n_channels=8, n_features=5, n_classes=4, hidden=16)
            x = torch.randn(6, 8, 5)
            logits = model(x)
            self.assertEqual(tuple(logits.shape), (6, 4), name)

    def test_dualview_prototype_loss_is_finite(self):
        model = build_model("dualview", n_channels=8, n_features=5, n_classes=4, hidden=16)
        x = torch.randn(6, 8, 5)
        y = torch.tensor([0, 1, 2, 3, 0, 1])
        embedding = model.embed(x)
        loss = model.prototype_regularization(embedding, y)
        self.assertTrue(torch.isfinite(loss))

    def test_eegnet_forward(self):
        model = build_model("eegnet", n_channels=8, n_features=256, n_classes=4)
        logits = model(torch.randn(5, 8, 256))
        self.assertEqual(tuple(logits.shape), (5, 4))


if __name__ == "__main__":
    unittest.main()
