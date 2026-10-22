from opendbc.car.hyundai.classic_long_aol import independent_buttons_qualified
from openpilot.starpilot.aol.intent import AolCardIntent


class ClassicLongCardIntent(AolCardIntent):
  def __init__(self, cp, settings):
    from openpilot.starpilot.car.hyundai.aol import independent_cruise_buttons_supported
    super().__init__(settings, explicit_latch=True, independent_cruise_buttons=(
      (independent_buttons_qualified(cp, marked_only=False) or independent_cruise_buttons_supported(cp)) and
      settings.lkas_action == 9 and settings.main_action == 0))
    self.requires_fault_observation = True
    from opendbc.car.hyundai.blended_stock_aol import qualified_alpha
    # Only the marked HDA2 owner retains an existing native LAT grant on pause.
    self.cancel_disarms_lateral = (qualified_alpha(cp) and cp.safetyConfigs[0].safetyParam == 0x2014 and
                                   cp.alternativeExperience != 32)
    self.observe_stock_engagement = True

  def _arm_from_full_engagement(self, CS, *, source_ns):
    if not (CS.steerFaultTemporary or CS.gasPressed or CS.brakePressed):
      super()._arm_from_full_engagement(CS, source_ns=source_ns)
