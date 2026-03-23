import numpy as np

from wattforest.metrics import PatternMetrics
from wattforest.state import CellVegetation, Cohort


def test_gap_metrics_return_expected_keys():
    metrics = PatternMetrics.gap_size_distribution(np.array([[0.1, 0.9], [0.2, 0.8]]))
    assert {"sizes_ha", "n_gaps", "fraction_in_gaps"} <= set(metrics)


def test_morans_i_uses_true_moore_neighborhood_weight_sum():
    values = np.array([[1.0, 0.0], [0.0, 1.0]])

    morans_i = PatternMetrics.morans_i(values)

    assert np.isclose(morans_i, -1.0 / 3.0)


def test_age_class_distribution_uses_dominant_cohorts_and_expected_bins():
    vegetation = np.empty((2, 2), dtype=object)
    vegetation[0, 0] = CellVegetation(
        cohorts=[
            Cohort(0, 12, 100.0, 10.0, 4.0, 0.1, 1.0),
            Cohort(1, 40, 100.0, 10.0, 8.0, 0.1, 1.0),
        ]
    )
    vegetation[0, 1] = CellVegetation(cohorts=[Cohort(0, 25, 100.0, 10.0, 7.0, 0.1, 1.0)])
    vegetation[1, 0] = CellVegetation(cohorts=[Cohort(0, 61, 100.0, 10.0, 9.0, 0.1, 1.0)])
    vegetation[1, 1] = CellVegetation()

    distribution = PatternMetrics.age_class_distribution(vegetation, bin_width_yr=20)

    assert distribution["counts"].tolist() == [0, 1, 1, 1]
    assert distribution["bin_edges"].tolist() == [0, 20, 40, 60, 80]
    assert distribution["mean_age"] == 42.0
