# Frozen host fit-boundary contract

Written before native output, 2026-10-22. Source starts at PR273 evidence head
805d9de27898b4a10e6212e65098d5995a40fdb1; numerical source is
d751ff28594902eca75d665ff116e662653481aa. No production source changes.

The generator `generate_motion_diagnostics.py` defines forward motion
`p=q+f/4*[3.25,-2.125]+f/4*A*(q-[64,48])`, with
`A=[[.012,-.008],[.006,-.010]]`. Correction truth is `q-p`, in original
pixels, with f=0..4 and pixel size .885 Angstrom. Model coordinates are
`x=q_x/128-.5`, `y=q_y/96-.5`; the model's frame is zero-based.
This gives X[3]=-.012*128/4=-.384, X[9]=+.008*96/4=.192,
Y[3]=-.006*128/4=-.192, Y[9]=+.010*96/4=.240; others zero
under exact global correction. These coefficients have pixel units because
the coordinates and frame indices are dimensionless.

Verified retained STARs have centers X={20,62,104}, Y={15,47,79}.
Native patch numbering is (iy+1,ix+1), so affine CUDA omits (2,1)=(20,47)
and noisy CUDA omits (1,3)=(104,15). CPU masks include all nine patches.
Every accepted patch has all five observations. The STAR writer truncates
`middle_frame+1` to int; default group=1 fit coordinates are f+.5, even
though serialized frame labels are f+1. No serialized coefficient is used.

Let `g*(f)=f*[-13/16,17/32]`, G be the chosen archived/global trajectory,
and `r(q)=(q-forward(q))/f`. Feed exact point residuals
`E_f=f*r(q)-G(f)` to the actual production `interpolateShifts`, which gives
origin `-.5*E_1`. The production default branch fits `E_f+.5*E_1` at
z=f+.5. With G=g*, these equal z times the affine rate; exact representability
is expected for every mask. This is an observation oracle, not a claim that
patch CCFs measure point residuals at patch centers.

For archived G, spatial and temporal sampling factor as a Cartesian product.
The six-column spatial matrix has full rank for each mask. The residual
decomposes into the same representable affine rate times z and a spatially
constant temporal term `h_f=g*(f)-G(f)+.5*(g*(1)-G(1))`.
The unique least-squares solution for that term is the three-vector
`(T^T T)^-1 T^T h`, T[f,k]=(f+.5)^(k+1). `freeze.py` computes this 3x5
projection with exact Fraction elimination, independently of the production
40/45-by-18 matrix and its SVD. `frozen.json` retains exact rational values.
NumPy is used only for rank/conditioning, not as an expected native solver.
At evaluation frame f, composed truth error is exactly
`P_h(f)+G(f)-g*(f)` and is spatially constant. Its predicted RMS values are
.24216226644651/.33292313430156 px for affine CPU/CUDA, and
.57515189013124/.40957204885978 px for noisy CPU/CUDA. These are
counterfactual composition characterizations, not accuracy floors or required
scientific passes.

Before native output, fixed absolute coefficient gate = 1e-7 px; fixed ROI
vector error against the analytic fit oracle = 2e-5 px. ROI is
x=12..115, y=12..83, f=0..4. Independent design conditioning is about
4069.25/4768.47/5399.94, minimum singular value >=.05538. Native rank must
be 18 at the unchanged solver cutoff 1e-10, and condition must be <6000.
The double-precision budget uses 32*m*n*epsilon*6000*2 < 7e-8 for
m<=45,n=18, coefficient norm scale <=2. ROI absolute basis sum <189
gives vector amplification sqrt(2)*189 and an error budget <1.9e-5 px.
This is an a priori conservative arithmetic acceptance budget, not a formal
forward-error theorem for Numerical Recipes SVD. No bit equality with NumPy
is asserted. Single-precision RFLOAT is outside this frozen contract and
fails explicitly rather than silently receiving a different tolerance.

Mutants negate residual sign, swap width/height normalization in the adapter,
or remove the .5 frame-center offset from fit input. They use the same oracle
and fixed bounds. No production mutation, new dependencies, gate/default
changes, serialization changes, scientific qualification or timing claims.

The test adapter is generated from the unchanged production block beginning
at the matA allocation and ending after its two solve calls. Configure rejects
missing/duplicate boundaries and tracks runner source changes. The original
upstream notice is retained. Only test target runner_numerics links it; actual
production interpolation, solve/SVD and model getShiftAt are used. The adapter
does not exercise the enclosing processMovie admission/publication logic,
which is a deliberate seam limitation. An independent CCF instrumentation
branch can change that source without a hunk conflict, but must preserve or
update these extraction boundaries if it edits the fitter.
