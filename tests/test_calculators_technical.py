from monaimetrics.calculators import (
    simple_moving_average,
    ma_slope,
    true_range,
    average_true_range,
    volume_ratio,
    relative_strength,
)


class TestSimpleMovingAverage:
    def test_basic(self):
        assert simple_moving_average([10, 20, 30]) == 20.0

    def test_with_period(self):
        assert simple_moving_average([1, 2, 3, 4, 5], period=3) == 4.0

    def test_empty(self):
        assert simple_moving_average([]) == 0.0

    def test_single_value(self):
        assert simple_moving_average([42.0]) == 42.0


class TestMASlope:
    def test_rising(self):
        prices = list(range(1, 200))
        slope = ma_slope(prices, period=150, lookback=10)
        assert slope > 0

    def test_falling(self):
        prices = list(range(200, 0, -1))
        slope = ma_slope(prices, period=150, lookback=10)
        assert slope < 0

    def test_insufficient_data(self):
        assert ma_slope([1, 2, 3], period=150, lookback=10) == 0.0


class TestTrueRange:
    def test_normal_bar(self):
        assert true_range(105, 95, 100) == 10

    def test_gap_up(self):
        tr = true_range(115, 110, 100)
        assert tr == 15  # high - prev_close

    def test_gap_down(self):
        tr = true_range(90, 85, 100)
        assert tr == 15  # prev_close - low


class TestATR:
    def test_basic(self):
        highs = [102, 104, 103, 105, 104, 106, 105, 107, 106, 108,
                 107, 109, 108, 110, 109, 111]
        lows =  [98,  99,  98, 100,  99, 101, 100, 102, 101, 103,
                 102, 104, 103, 105, 104, 106]
        closes = [100, 101, 100, 102, 101, 103, 102, 104, 103, 105,
                  104, 106, 105, 107, 106, 108]
        atr = average_true_range(highs, lows, closes, period=14)
        assert atr > 0

    def test_insufficient_data(self):
        assert average_true_range([100], [95], [98], period=14) == 0.0


class TestVolumeRatio:
    def test_double_volume(self):
        assert volume_ratio(2000000, 1000000) == 2.0

    def test_zero_average(self):
        assert volume_ratio(1000000, 0) == 0.0

    def test_below_average(self):
        assert volume_ratio(500000, 1000000) == 0.5


class TestRelativeStrength:
    def test_outperformer(self):
        score = relative_strength(0.20, 0.10)
        assert score > 50

    def test_underperformer(self):
        score = relative_strength(0.05, 0.15)
        assert score < 50

    def test_matching(self):
        score = relative_strength(0.10, 0.10)
        assert score == 50.0

    def test_clamped(self):
        score = relative_strength(1.0, -1.0)
        assert score == 100.0
