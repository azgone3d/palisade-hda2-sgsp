# SGSP integration status — October 27, 2026

Source merge of upstream SecretGoodStarPilot 2dfa4b6fe19c695c386fc6b5c6d821f8a2030139 into custom testing head 5c989ba751b2a72a28ac2f218259c9b9fe2e79a9.

This branch is NOT qualified for installation or road use. The existing driving branch and PR #247 are unchanged.

## Resolution

Resolved 23 conflicted files. Retained scoped Palisade independent LKAS/Main policy, physical cancel/brake timestamps, bounded intent retention, firmware identities, camera scheduling, launch ceiling-boost exclusion, lifetime history and neon/telemetry customization. Incorporated upstream Galaxy analysis, layout schema/navigation/Jetlink widgets, Bluetooth ENOSYS retries, shared AOL handling and longitudinal changes. Native Palisade status ownership retains the custom branch policy; upstream other-profile policies remain present.

## Completed validation

- Eight Bluetooth socket unit tests passed.
- Galaxy home and onroad-layout JavaScript suites passed.
- 34 history/pure launch regressions passed; 27 runtime-dependent cases excluded after confirming their required compiled libraries are unavailable.
- 1203 changed Python files parsed without syntax errors.
- Undefined-symbol, duplicate-definition and unused-import checks passed on seven conflict-sensitive production modules.

## Required before updating the driving branch or installing

- Build the native libraries for the merged source and supported Python runtime. Current WSL runtime is Python 3.14; this tree requires Python 3.12. Native Params and messaging libraries are missing/unusable here.
- Run the full Palisade host/native, source-deadline, cancel/brake, camera-copy, startup and neighboring-profile regressions against the actual merged tree.
- Run the UI/telemetry/projection tests with native messaging available and inspect rendered layouts.
- Rebuild and verify matching Panda firmware and protected-source/prebuilt receipts. Upstream firmware artifacts do not qualify the modified custom safety tree. Do not bypass receipt validation or copy an upstream receipt as proof of this integration.
- Review the combined custom stopping buffer and upstream HKG vision-stop buffer; neither constitutes a fix for missed model detections or establishes safe on-road behavior.

No device files or settings were changed. No upstream PR was modified.
