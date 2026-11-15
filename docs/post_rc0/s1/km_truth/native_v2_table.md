
## Native v2 per-case field errors

RMS/P95/max are vector errors in the fixed interior ROI. `INPUT_ERROR` is the original checker outcome; its field-only distances below are an independent diagnostic. All native process exits are 0.

|Backend|Case|RMS/P95/max px|RMS/P95/max Å|Original checker|Global converged|
|---|---|---|---|---|---|
|cpu|zero|0.00000/0.00000/0.00000|0.00000/0.00000/0.00000|PASS|yes|
|cpu|integer|0.29787/0.48769/0.48769|0.26361/0.43161/0.43161|FAIL|no|
|cpu|fractional|0.59215/0.79482/0.79482|0.52406/0.70342/0.70342|FAIL|no|
|cpu|affine|0.45474/0.83897/1.02951|0.40245/0.74249/0.91112|FAIL|yes|
|cpu|pedestal|2.39450/4.07204/4.39900|2.11913/3.60376/3.89311|FAIL|yes|
|cpu|noisy|2.64742/4.94528/11.19089|2.34296/4.37657/9.90394|INPUT_ERROR_OUTSIDE_ROI|no|
|cpu|flat|2.37788/3.88306/3.88306|2.10442/3.43650/3.43650|UNIDENTIFIABLE|yes|
|cpu|repeated|18.68233/31.64284/31.64284|16.53386/28.00392/28.00392|INPUT_ERROR_OUTSIDE_ROI|yes|
|cuda|zero|0.00000/0.00000/0.00000|0.00000/0.00000/0.00000|PASS|yes|
|cuda|integer|0.51480/0.64684/0.64684|0.45560/0.57245/0.57245|FAIL|no|
|cuda|fractional|0.33908/0.53125/0.53125|0.30008/0.47016/0.47016|FAIL|yes|
|cuda|affine|0.34880/0.66417/0.92789|0.30869/0.58779/0.82118|FAIL|yes|
|cuda|pedestal|2.39450/4.07204/4.39900|2.11913/3.60376/3.89311|FAIL|yes|
|cuda|noisy|1.69206/3.15850/7.10720|1.49747/2.79527/6.28987|FAIL|yes|
|cuda|flat|2.37788/3.88306/3.88306|2.10442/3.43650/3.43650|UNIDENTIFIABLE|yes|
|cuda|repeated|67.56902/95.61878/95.61878|59.79859/84.62262/84.62262|INPUT_ERROR_OUTSIDE_ROI|no|
