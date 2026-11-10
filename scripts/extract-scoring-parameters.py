#!/usr/bin/env python3
"""Writes the scoringParameters sets of a MATSim config into a config of their own, which rust and DSim both read.

    python3 scripts/extract-scoring-parameters.py <calibrated output_config_reduced.xml> <output scoring.xml>

Only the scoringParameters sets of the scoring module are kept. The parameters of the module itself
(fractionOfIterationsToStartScoreMSA, writeExperiencedPlans, ...) are left out, so that reading the file on top of a
run config does not change them. Other modules, e.g. advancedScoring, are left out as well. Comments are dropped.

The tasteVariations sets inside the scoringParameters sets are removed: with them, MATSim scores with
IndividualPersonScoringParameters (income-dependent marginal utility of money, ASCs per person), which rust does not
support. Without them, both use the same parameters for every person of a subpopulation.

Stage activities (types ending with "interaction") without scoringThisActivityAtAll get it set to false. A reduced
output config leaves it out for the stage activities that MATSim's default config already contains (e.g. car
interaction), but read on its own, MATSim would then score them and fail on their undefined typical duration. rust
treats these types as not scored anyway.
"""
import sys
import xml.etree.ElementTree as ET

HEADER = ('<?xml version="1.0" encoding="UTF-8"?>\n'
          '<!DOCTYPE config SYSTEM "http://www.matsim.org/files/dtd/config_v2.dtd">\n')


def main(source: str, target: str):
    module = ET.parse(source).getroot().find("module[@name='scoring']")
    if module is None:
        sys.exit(f"{source} has no scoring module.")
    sets = module.findall("parameterset[@type='scoringParameters']")
    if not sets:
        sys.exit(f"The scoring module of {source} has no scoringParameters sets.")
    for parameter_set in sets:
        for variations in parameter_set.findall("parameterset[@type='tasteVariations']"):
            parameter_set.remove(variations)
        for activity in parameter_set.findall("parameterset[@type='activityParams']"):
            params = {p.get("name"): p for p in activity.findall("param")}
            is_stage = params.get("activityType") is not None and params["activityType"].get("value").endswith("interaction")
            if is_stage and "scoringThisActivityAtAll" not in params:
                ET.SubElement(activity, "param", name="scoringThisActivityAtAll", value="false")

    config = ET.Element("config")
    scoring = ET.SubElement(config, "module", name="scoring")
    scoring.extend(sets)
    ET.indent(config, space="\t")
    with open(target, "w", encoding="utf-8") as f:
        f.write(HEADER)
        f.write(f"<!-- scoringParameters sets of {source.split('/')[-1]}, written by "
                f"scripts/extract-scoring-parameters.py of parallel-qsim-berlin -->\n")
        f.write(ET.tostring(config, encoding="unicode"))
        f.write("\n")
    print(f"{target}: {len(sets)} scoringParameters sets")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
