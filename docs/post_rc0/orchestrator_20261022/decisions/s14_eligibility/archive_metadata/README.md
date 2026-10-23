# Official acquisition-metadata cross-check (still not admission)

Four bounded HTTPS metadata GETs to the official EMBL-EBI EMPIAR API succeeded
on 22 October 2026. The web tool could not open these API URLs; curl fetched JSON
instead. `retrieval.json` records URLs, status, hashes and the selected-field
snapshots. Only metadata fields needed for this check are copied, without author
contact records. No movie/gain/particle/map was acquired or decoded and no new
candidate scientific outcome was read. These are archive assertions, not an
independent examination of each local file or acquisition session.

| Family | Archive declaration versus operational recipe | Result / remaining question |
| --- | --- | --- |
| EMPIAR-10641 | Archive: 5760×4092, 70 frames, 0.4 Å/pixel, unsigned-byte TIFF; recipe agrees. API identifies a K3 CDS acquisition, supplied gain and deposited particle metadata path. | Geometry/pixel-size recipe corroborated. This API response supplies no dose or gain-transform validation; particle metadata availability on the archive does not mean a complete local matched design exists. |
| EMPIAR-10216 | Archive: 4096², 59 frames, 0.517 Å/pixel, unsigned-16 MRC; recipe agrees. The archive describes separate particle STARs before polishing and after polishing/CTF refinement. | Geometry/pixel-size recipe corroborated. Use the appropriate pre-re-estimation reference design, not a silently substituted polished result. Dose is still a recipe placeholder pending acquisition evidence. |
| EMPIAR-10474 Falcon3 / Falcon4 | Archive: 4096², 1.06 / 1.64 Å/pixel, 2331 / 5782 EER frames; recipes use 58 / 144 grouped frames with grouping 40. | Spatial recipe agrees with archive fields. Raw event-frame counts and grouped output-frame counts are distinct; actual per-file grouping, retained exposure, dose and partial-group handling remain to be traced. No equality of those frame counts is asserted. |
| EMPIAR-12963 | Archive raw EER: 8192², 40 nominal frames, 0.97 Å/pixel; gain entry also 8192². Archive corrected images: 4096², 0.49 Å/pixel. Operational recipe: 4096², 39 grouped frames, grouping 49, 0.97 Å/pixel and nominal total50/39 dose. | Mapping remains unresolved. The API may describe different rendering/sampling conventions; these differences alone do not prove the recipe is wrong. Trace actual EER/gain headers, rendering/super-resolution, acquisition XML and group exposure before a science freeze. Do not silently change the current campaign. |

The archive titles distinguish the biological entries (streptavidin, apoferritin
and a nucleosome specimen), but this is not complete specimen/session provenance
or a proof of independent processing. No licence field is present in these API
responses; this check therefore does **not** mark licensing verified. Directory
and particle-pattern fields describe archive availability, not a newly staged
local downstream workflow, half-set assignment or sufficient statistical sample.
The provisional eligibility states remain INCOMPLETE.

Sources: [10641](https://www.ebi.ac.uk/empiar/api/entry/10641/),
[10216](https://www.ebi.ac.uk/empiar/api/entry/10216/),
[10474](https://www.ebi.ac.uk/empiar/api/entry/10474/),
[12963](https://www.ebi.ac.uk/empiar/api/entry/12963/).
No reference gate, legacy recipe, old PASS/FAIL or corrected-image result is
reclassified by this metadata check. The frozen DC compatibility campaign and
C1 qualification keep their recorded inputs/options; this work only informs the
future S1.4 admission/protocol.
