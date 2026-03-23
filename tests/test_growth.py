import numpy as np

from wattforest.climate import ClimateLayers
from wattforest.modules.growth import GrowthModule
from wattforest.soils import SoilLayers
from wattforest.species import SpeciesParams
from wattforest.state import Cohort


def test_growth_returns_non_negative_increment():
    module = GrowthModule()
    cohort = Cohort(0, 10, 100.0, 1000.0, 5.0, 0.2, 1.0)
    species = SpeciesParams(
        species_id=0,
        name="test",
        pft="pioneer",
        d_max_cm=80.0,
        h_max_m=35.0,
        age_max_yr=200,
        g_max_cm_yr=0.5,
        specific_leaf_area=10.0,
        wood_density_kg_m3=500.0,
        shade_tolerance=2.0,
        light_compensation_frac=0.1,
        light_saturation_frac=0.8,
        gdd_min=500.0,
        gdd_max=3000.0,
        drought_tolerance=0.5,
        frost_tolerance=100.0,
        background_mortality_yr=0.01,
        stress_mortality_threshold=0.3,
        stress_mortality_rate=0.2,
        maturity_age_yr=15,
        fecundity_seeds_yr=1000.0,
        seed_mass_g=0.5,
        dispersal_mean_m=50.0,
        dispersal_fat_tail_p=2.0,
        leaf_litter_bulk_density=20.0,
        flammability=0.5,
    )
    climate = ClimateLayers(
        growing_degree_days=np.array([[1500.0]]),
        annual_precip_mm=np.array([[1000.0]]),
        drought_index=np.array([[0.2]]),
        frost_free_days=np.array([[150]]),
    )
    soils = SoilLayers(
        awc=np.array([[120.0]]),
        depth_to_restriction=np.array([[100.0]]),
        texture_class=np.array([[1]], dtype=np.uint8),
        rock_fraction=np.array([[0.1]]),
    )
    assert module.grow_cohort(cohort, species, 0.8, climate, soils, 0, 0) >= 0.0
