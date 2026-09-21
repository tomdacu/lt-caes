# LTA / LTAHP-CAES research map

This directory is a curated, public-facing reading map for the project. It
links original publications, research groups, and related open software; it
does **not** redistribute PDFs from the private research collection or material
whose licence is unclear.

The project extends the established low-temperature adiabatic CAES literature
into two simulator forms: **LTA-CAES (low-temperature adiabatic CAES)**,
selected by `heat_offtake = "none"`, and **LTAHP-CAES (low-temperature
adiabatic heat and power CAES)**, selected by `heat_offtake = "heat_user"`. The
liquid-TES attraction is not a claim of the
highest possible round-trip efficiency; it is the use of a cheap, available,
benign heat-transfer medium and conventional exchangers at less demanding
temperatures than high-temperature A-CAES.

Literature **AA-CAES** means advanced adiabatic CAES. It is retained in paper
titles and summaries; AA-CAES is not this repository's abbreviation, and the
repository simulates the low-temperature forms only.

Start with:

1. [LTA-CAES literature](LITERATURE.md) for the technical and economic basis.
2. [People, groups, and software](PEOPLE_AND_GROUPS.md) for researchers and
   tools worth following.
3. [Model scope](../02_PHYSICS_AND_MODEL_BOUNDARY.md) for the normalized two-tank assumptions and
   the dynamic or equipment-sizing effects intentionally deferred.
4. [LTAHP-CAES literature and the Denmark opportunity](LTAHP_CAES_AND_DENMARK.md)
   for the district-heating and salt-cavern research case.
5. [LTAHP-CAES heat rejection, cogeneration, and citation map](LTAHP_CAES_HEAT_REJECTION_AND_COGENERATION.md)
   for the E-303 audit, heat-recovery alternatives and ranked literature.

## How to contribute a source

Add only sources directly relevant to the two low-temperature CAES forms,
thermal energy storage, district energy, heat exchangers, or turbomachinery. Prefer a DOI, publisher page,
institutional repository, or official project page. Include one sentence on
why the source matters to this simulator.
