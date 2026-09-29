import unittest

import services


class ServicesRoundingTests(unittest.TestCase):
    def test_round5_rounds_money_to_two_decimals(self):
        self.assertEqual(services.round5(10.005), 10.01)

    def test_round5_keeps_integral_values_as_ints(self):
        self.assertEqual(services.round5(5.0), 5)


if __name__ == "__main__":
    unittest.main()
