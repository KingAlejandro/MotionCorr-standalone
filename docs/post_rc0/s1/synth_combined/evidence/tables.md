native runs 410; nonzero exits 0

### Per condition and arm (median over seeds)

|Condition|Arm|n|Field RMS px|Transfer in-band|T 0.01-.04|.04-.08|.08-.12|.12-.16|FRC|relRMSE|Border rel.RMS|Interior px rel.RMS|
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
|dose05|cpu-none|10|0.42969|0.9884|0.998|0.987|0.969|0.943|0.544|1.525|3.898|3.948|
|dose05|cpu-both|10|0.42998|0.9884|0.998|0.987|0.969|0.943|0.544|1.525|3.897|3.947|
|dose05|cuda-none|10|0.43045|0.9885|0.998|0.987|0.969|0.943|0.544|1.525|3.897|3.948|
|dose05|cuda-both|10|0.42998|0.9884|0.998|0.987|0.969|0.943|0.544|1.525|3.897|3.947|
|dose1|cpu-none|10|0.2992|0.9911|1|0.989|0.975|0.954|0.676|1.081|2.769|2.823|
|dose1|cpu-both|10|0.29918|0.9911|1|0.989|0.975|0.954|0.676|1.081|2.769|2.823|
|dose1|cuda-none|10|0.29894|0.9911|1|0.989|0.975|0.954|0.676|1.081|2.769|2.823|
|dose1|cuda-both|10|0.29918|0.9911|1|0.989|0.975|0.954|0.676|1.081|2.769|2.823|
|dose2|cpu-none|10|0.19938|0.9915|0.996|0.991|0.98|0.954|0.791|0.7661|1.983|2.006|
|dose2|cpu-both|10|0.19996|0.9915|0.996|0.991|0.98|0.954|0.791|0.766|1.984|2.005|
|dose2|cuda-none|10|0.19951|0.9914|0.996|0.991|0.98|0.954|0.791|0.766|1.983|2.005|
|dose2|cuda-both|10|0.19996|0.9915|0.996|0.991|0.98|0.954|0.791|0.766|1.984|2.005|
|dose4|cpu-none|10|0.13369|0.9921|0.997|0.992|0.977|0.959|0.878|0.5406|1.408|1.414|
|dose4|cpu-both|10|0.13356|0.9922|0.997|0.992|0.977|0.959|0.878|0.5406|1.409|1.415|
|dose4|cuda-none|10|0.13272|0.9921|0.997|0.992|0.977|0.959|0.878|0.5406|1.409|1.414|
|dose4|cuda-both|10|0.13356|0.9922|0.997|0.992|0.977|0.959|0.878|0.5406|1.409|1.415|
|outmodel|cpu-none|10|1.0425|0.9614|0.991|0.958|0.894|0.794|0.658|1.101|2.777|2.821|
|outmodel|cpu-both|10|1.0424|0.9614|0.991|0.958|0.894|0.794|0.658|1.1|2.778|2.821|
|outmodel|cuda-none|10|1.0423|0.9614|0.991|0.958|0.894|0.794|0.658|1.1|2.778|2.82|
|outmodel|cuda-both|10|1.0424|0.9614|0.991|0.958|0.894|0.794|0.658|1.1|2.778|2.821|
|nonsquare|cpu-none|10|0.24627|0.9908|0.998|0.99|0.975|0.937|0.676|1.083|2.753|2.803|
|nonsquare|cpu-both|10|0.24611|0.9907|0.998|0.99|0.975|0.937|0.676|1.083|2.753|2.804|
|nonsquare|cuda-none|10|0.2456|0.9908|0.998|0.99|0.975|0.937|0.676|1.083|2.753|2.803|
|nonsquare|cuda-both|10|0.24611|0.9907|0.998|0.99|0.975|0.937|0.676|1.083|2.753|2.804|
|pedestal0|cpu-none|10|0.29918|0.9911|1|0.989|0.975|0.954|0.676|1.081|2.769|2.823|
|pedestal0|cpu-both|10|0.29918|0.9911|1|0.989|0.975|0.954|0.676|1.081|2.769|2.823|
|pedestal0|cuda-none|10|0.29918|0.9911|1|0.989|0.975|0.954|0.676|1.081|2.769|2.823|
|pedestal0|cuda-both|10|0.29918|0.9911|1|0.989|0.975|0.954|0.676|1.081|2.769|2.823|
|pedestal32|cpu-none|10|1.7878|0.9262|0.98|0.917|0.804|0.659|0.628|1.151|3.979|3.965|
|pedestal32|cpu-both|10|0.29919|0.9911|1|0.989|0.975|0.954|0.676|1.081|2.769|2.823|
|pedestal32|cuda-none|10|1.7383|0.9308|0.983|0.923|0.815|0.641|0.628|1.156|3.975|3.966|
|pedestal32|cuda-both|10|0.29918|0.9911|1|0.989|0.975|0.954|0.676|1.081|2.769|2.823|
|pedestal32|cpu-double|10|0.29919|0.9911|1|0.989|0.975|0.954|0.676|1.081|2.769|2.823|
|contrast025|cpu-none|10|0.31416|0.9908|1|0.989|0.975|0.954|0.676|1.081|2.767|2.824|
|contrast025|cpu-both|10|0.29918|0.9911|1|0.989|0.975|0.954|0.676|1.081|2.769|2.823|
|contrast025|cuda-none|10|0.29715|0.9909|1|0.99|0.975|0.953|0.676|1.082|2.759|2.823|
|contrast025|cuda-both|10|0.29918|0.9911|1|0.989|0.975|0.954|0.676|1.081|2.769|2.823|
|contrast4|cpu-none|10|0.29917|0.9911|1|0.989|0.975|0.954|0.676|1.081|2.769|2.823|
|contrast4|cpu-both|10|0.29918|0.9911|1|0.989|0.975|0.954|0.676|1.081|2.769|2.823|
|contrast4|cuda-none|10|0.29917|0.9911|1|0.989|0.975|0.954|0.676|1.081|2.769|2.823|
|contrast4|cuda-both|10|0.29918|0.9911|1|0.989|0.975|0.954|0.676|1.081|2.769|2.823|

### Paired per-seed sign tests (b relative to a; "improves" = better for that metric; exact two-sided, ties |d|<=1e-9)

|Condition|Comparison|Metric|wins/losses/ties|median delta|p|label|
|---|---|---|---|---:|---:|---|
|dose05|DC none -> both (CPU)|field RMS|5/5/0|5.72e-05|1|neutral/mixed|
|dose05|DC none -> both (CPU)|image transfer (in-band)|4/6/0|2.77e-06|0.7539|neutral/mixed|
|dose05|DC none -> both (CPU)|image relRMSE (in-band)|4/6/0|1.65e-05|0.7539|neutral/mixed|
|dose05|DC none -> both (CPU)|border rel.RMS|8/2/0|-0.00115|0.1094|neutral/mixed|
|dose05|DC none -> both (CUDA)|field RMS|4/6/0|0.000133|0.7539|neutral/mixed|
|dose05|DC none -> both (CUDA)|image transfer (in-band)|3/7/0|2.23e-05|0.3438|neutral/mixed|
|dose05|DC none -> both (CUDA)|image relRMSE (in-band)|6/4/0|-3.27e-05|0.7539|neutral/mixed|
|dose05|DC none -> both (CUDA)|border rel.RMS|6/4/0|-0.000232|0.7539|neutral/mixed|
|dose05|CPU -> CUDA (DC none)|field RMS|6/4/0|-0.000237|0.7539|neutral/mixed|
|dose05|CPU -> CUDA (DC none)|image transfer (in-band)|7/3/0|-1.53e-05|0.3438|neutral/mixed|
|dose05|CPU -> CUDA (DC none)|image relRMSE (in-band)|4/6/0|3.72e-05|0.7539|neutral/mixed|
|dose05|CPU -> CUDA (DC none)|border rel.RMS|6/4/0|-0.000458|0.7539|neutral/mixed|
|dose05|CPU -> CUDA (DC both)|field RMS|2/8/0|2.69e-07|0.1094|neutral/mixed|
|dose05|CPU -> CUDA (DC both)|image transfer (in-band)|5/5/0|6.63e-09|1|neutral/mixed|
|dose05|CPU -> CUDA (DC both)|image relRMSE (in-band)|9/1/0|-2.16e-07|0.02148|improves|
|dose05|CPU -> CUDA (DC both)|border rel.RMS|9/1/0|-1.54e-06|0.02148|improves|
|dose1|DC none -> both (CPU)|field RMS|6/4/0|-4.17e-05|0.7539|neutral/mixed|
|dose1|DC none -> both (CPU)|image transfer (in-band)|6/4/0|-1.14e-05|0.7539|neutral/mixed|
|dose1|DC none -> both (CPU)|image relRMSE (in-band)|4/6/0|3.39e-05|0.7539|neutral/mixed|
|dose1|DC none -> both (CPU)|border rel.RMS|6/4/0|-3.02e-05|0.7539|neutral/mixed|
|dose1|DC none -> both (CUDA)|field RMS|4/6/0|0.000177|0.7539|neutral/mixed|
|dose1|DC none -> both (CUDA)|image transfer (in-band)|3/7/0|1.59e-05|0.3438|neutral/mixed|
|dose1|DC none -> both (CUDA)|image relRMSE (in-band)|6/4/0|-4.43e-05|0.7539|neutral/mixed|
|dose1|DC none -> both (CUDA)|border rel.RMS|5/5/0|6.15e-05|1|neutral/mixed|
|dose1|CPU -> CUDA (DC none)|field RMS|5/5/0|-5.24e-05|1|neutral/mixed|
|dose1|CPU -> CUDA (DC none)|image transfer (in-band)|8/2/0|-1.51e-05|0.1094|neutral/mixed|
|dose1|CPU -> CUDA (DC none)|image relRMSE (in-band)|2/8/0|3.82e-05|0.1094|neutral/mixed|
|dose1|CPU -> CUDA (DC none)|border rel.RMS|5/5/0|5.66e-05|1|neutral/mixed|
|dose1|CPU -> CUDA (DC both)|field RMS|6/4/0|-6.57e-08|0.7539|neutral/mixed|
|dose1|CPU -> CUDA (DC both)|image transfer (in-band)|2/8/0|2.79e-07|0.1094|neutral/mixed|
|dose1|CPU -> CUDA (DC both)|image relRMSE (in-band)|9/1/0|-1.72e-07|0.02148|improves|
|dose1|CPU -> CUDA (DC both)|border rel.RMS|10/0/0|-1.02e-06|0.001953|improves|
|dose2|DC none -> both (CPU)|field RMS|4/6/0|0.000245|0.7539|neutral/mixed|
|dose2|DC none -> both (CPU)|image transfer (in-band)|5/5/0|2.33e-06|1|neutral/mixed|
|dose2|DC none -> both (CPU)|image relRMSE (in-band)|5/5/0|4e-06|1|neutral/mixed|
|dose2|DC none -> both (CPU)|border rel.RMS|5/5/0|-8.8e-05|1|neutral/mixed|
|dose2|DC none -> both (CUDA)|field RMS|2/8/0|0.000397|0.1094|neutral/mixed|
|dose2|DC none -> both (CUDA)|image transfer (in-band)|6/4/0|-7.32e-06|0.7539|neutral/mixed|
|dose2|DC none -> both (CUDA)|image relRMSE (in-band)|3/7/0|2.68e-05|0.3438|neutral/mixed|
|dose2|DC none -> both (CUDA)|border rel.RMS|4/6/0|6.36e-06|0.7539|neutral/mixed|
|dose2|CPU -> CUDA (DC none)|field RMS|6/4/0|-0.000109|0.7539|neutral/mixed|
|dose2|CPU -> CUDA (DC none)|image transfer (in-band)|4/6/0|1e-05|0.7539|neutral/mixed|
|dose2|CPU -> CUDA (DC none)|image relRMSE (in-band)|7/3/0|-4.03e-05|0.3438|neutral/mixed|
|dose2|CPU -> CUDA (DC none)|border rel.RMS|6/4/0|-0.000244|0.7539|neutral/mixed|
|dose2|CPU -> CUDA (DC both)|field RMS|3/7/0|6.86e-08|0.3438|neutral/mixed|
|dose2|CPU -> CUDA (DC both)|image transfer (in-band)|2/8/0|2.7e-07|0.1094|neutral/mixed|
|dose2|CPU -> CUDA (DC both)|image relRMSE (in-band)|9/1/0|-1.82e-07|0.02148|improves|
|dose2|CPU -> CUDA (DC both)|border rel.RMS|7/3/0|-4.88e-07|0.3438|neutral/mixed|
|dose4|DC none -> both (CPU)|field RMS|7/3/0|-0.000341|0.3438|neutral/mixed|
|dose4|DC none -> both (CPU)|image transfer (in-band)|8/2/0|-7.51e-06|0.1094|neutral/mixed|
|dose4|DC none -> both (CPU)|image relRMSE (in-band)|3/7/0|1.02e-05|0.3438|neutral/mixed|
|dose4|DC none -> both (CPU)|border rel.RMS|4/6/0|0.00017|0.7539|neutral/mixed|
|dose4|DC none -> both (CUDA)|field RMS|5/5/0|0.000103|1|neutral/mixed|
|dose4|DC none -> both (CUDA)|image transfer (in-band)|6/4/0|-7.13e-06|0.7539|neutral/mixed|
|dose4|DC none -> both (CUDA)|image relRMSE (in-band)|5/5/0|7.13e-06|1|neutral/mixed|
|dose4|DC none -> both (CUDA)|border rel.RMS|5/5/0|6.63e-05|1|neutral/mixed|
|dose4|CPU -> CUDA (DC none)|field RMS|8/2/0|-0.0006|0.1094|neutral/mixed|
|dose4|CPU -> CUDA (DC none)|image transfer (in-band)|5/5/0|-5.14e-06|1|neutral/mixed|
|dose4|CPU -> CUDA (DC none)|image relRMSE (in-band)|5/5/0|5.48e-06|1|neutral/mixed|
|dose4|CPU -> CUDA (DC none)|border rel.RMS|5/5/0|1.22e-05|1|neutral/mixed|
|dose4|CPU -> CUDA (DC both)|field RMS|4/6/0|6.58e-08|0.7539|neutral/mixed|
|dose4|CPU -> CUDA (DC both)|image transfer (in-band)|0/10/0|2.14e-07|0.001953|harms|
|dose4|CPU -> CUDA (DC both)|image relRMSE (in-band)|10/0/0|-1.48e-07|0.001953|improves|
|dose4|CPU -> CUDA (DC both)|border rel.RMS|8/2/0|-4.19e-07|0.1094|neutral/mixed|
|outmodel|DC none -> both (CPU)|field RMS|5/5/0|-2.1e-05|1|neutral/mixed|
|outmodel|DC none -> both (CPU)|image transfer (in-band)|6/4/0|-7.16e-06|0.7539|neutral/mixed|
|outmodel|DC none -> both (CPU)|image relRMSE (in-band)|4/6/0|1.68e-05|0.7539|neutral/mixed|
|outmodel|DC none -> both (CPU)|border rel.RMS|3/7/0|0.000147|0.3438|neutral/mixed|
|outmodel|DC none -> both (CUDA)|field RMS|7/3/0|-0.000106|0.3438|neutral/mixed|
|outmodel|DC none -> both (CUDA)|image transfer (in-band)|10/0/0|-1.99e-05|0.001953|improves|
|outmodel|DC none -> both (CUDA)|image relRMSE (in-band)|2/8/0|4.66e-05|0.1094|neutral/mixed|
|outmodel|DC none -> both (CUDA)|border rel.RMS|3/7/0|0.000151|0.3438|neutral/mixed|
|outmodel|CPU -> CUDA (DC none)|field RMS|4/6/0|9.49e-05|0.7539|neutral/mixed|
|outmodel|CPU -> CUDA (DC none)|image transfer (in-band)|2/8/0|2.08e-05|0.1094|neutral/mixed|
|outmodel|CPU -> CUDA (DC none)|image relRMSE (in-band)|7/3/0|-5.96e-05|0.3438|neutral/mixed|
|outmodel|CPU -> CUDA (DC none)|border rel.RMS|4/6/0|9.59e-05|0.7539|neutral/mixed|
|outmodel|CPU -> CUDA (DC both)|field RMS|4/6/0|3.17e-08|0.7539|neutral/mixed|
|outmodel|CPU -> CUDA (DC both)|image transfer (in-band)|3/7/0|2.54e-07|0.3438|neutral/mixed|
|outmodel|CPU -> CUDA (DC both)|image relRMSE (in-band)|10/0/0|-4.29e-07|0.001953|improves|
|outmodel|CPU -> CUDA (DC both)|border rel.RMS|9/1/0|-6.75e-07|0.02148|improves|
|nonsquare|DC none -> both (CPU)|field RMS|6/4/0|-0.000376|0.7539|neutral/mixed|
|nonsquare|DC none -> both (CPU)|image transfer (in-band)|3/7/0|7.57e-06|0.3438|neutral/mixed|
|nonsquare|DC none -> both (CPU)|image relRMSE (in-band)|7/3/0|-2.29e-05|0.3438|neutral/mixed|
|nonsquare|DC none -> both (CPU)|border rel.RMS|2/8/0|0.000685|0.1094|neutral/mixed|
|nonsquare|DC none -> both (CUDA)|field RMS|5/5/0|-9.78e-05|1|neutral/mixed|
|nonsquare|DC none -> both (CUDA)|image transfer (in-band)|2/8/0|9.86e-06|0.1094|neutral/mixed|
|nonsquare|DC none -> both (CUDA)|image relRMSE (in-band)|7/3/0|-2.47e-05|0.3438|neutral/mixed|
|nonsquare|DC none -> both (CUDA)|border rel.RMS|4/6/0|0.000331|0.7539|neutral/mixed|
|nonsquare|CPU -> CUDA (DC none)|field RMS|6/4/0|-0.000294|0.7539|neutral/mixed|
|nonsquare|CPU -> CUDA (DC none)|image transfer (in-band)|6/4/0|-5.56e-06|0.7539|neutral/mixed|
|nonsquare|CPU -> CUDA (DC none)|image relRMSE (in-band)|4/6/0|3.92e-06|0.7539|neutral/mixed|
|nonsquare|CPU -> CUDA (DC none)|border rel.RMS|4/6/0|0.000196|0.7539|neutral/mixed|
|nonsquare|CPU -> CUDA (DC both)|field RMS|1/9/0|2.26e-07|0.02148|harms|
|nonsquare|CPU -> CUDA (DC both)|image transfer (in-band)|0/10/0|3.28e-07|0.001953|harms|
|nonsquare|CPU -> CUDA (DC both)|image relRMSE (in-band)|7/3/0|-3.78e-08|0.3438|neutral/mixed|
|nonsquare|CPU -> CUDA (DC both)|border rel.RMS|7/3/0|-2.14e-07|0.3438|neutral/mixed|
|pedestal0|DC none -> both (CPU)|field RMS|7/3/0|-1.51e-07|0.3438|neutral/mixed|
|pedestal0|DC none -> both (CPU)|image transfer (in-band)|6/4/0|-3.27e-09|0.7539|neutral/mixed|
|pedestal0|DC none -> both (CPU)|image relRMSE (in-band)|3/7/0|1.18e-08|0.3438|neutral/mixed|
|pedestal0|DC none -> both (CPU)|border rel.RMS|7/3/0|-1.2e-07|0.3438|neutral/mixed|
|pedestal0|DC none -> both (CUDA)|field RMS|4/6/0|1.2e-07|0.7539|neutral/mixed|
|pedestal0|DC none -> both (CUDA)|image transfer (in-band)|4/5/1|1.58e-09|1|neutral/mixed|
|pedestal0|DC none -> both (CUDA)|image relRMSE (in-band)|5/5/0|-5.79e-09|1|neutral/mixed|
|pedestal0|DC none -> both (CUDA)|border rel.RMS|4/6/0|2.55e-08|0.7539|neutral/mixed|
|pedestal0|CPU -> CUDA (DC none)|field RMS|4/6/0|4.56e-08|0.7539|neutral/mixed|
|pedestal0|CPU -> CUDA (DC none)|image transfer (in-band)|2/8/0|2.92e-07|0.1094|neutral/mixed|
|pedestal0|CPU -> CUDA (DC none)|image relRMSE (in-band)|9/1/0|-1.87e-07|0.02148|improves|
|pedestal0|CPU -> CUDA (DC none)|border rel.RMS|10/0/0|-1.07e-06|0.001953|improves|
|pedestal0|CPU -> CUDA (DC both)|field RMS|4/6/0|9.5e-08|0.7539|neutral/mixed|
|pedestal0|CPU -> CUDA (DC both)|image transfer (in-band)|2/8/0|2.74e-07|0.1094|neutral/mixed|
|pedestal0|CPU -> CUDA (DC both)|image relRMSE (in-band)|9/1/0|-1.92e-07|0.02148|improves|
|pedestal0|CPU -> CUDA (DC both)|border rel.RMS|9/1/0|-1.02e-06|0.02148|improves|
|pedestal32|DC none -> both (CPU)|field RMS|10/0/0|-1.52|0.001953|improves|
|pedestal32|DC none -> both (CPU)|image transfer (in-band)|10/0/0|-0.0655|0.001953|improves|
|pedestal32|DC none -> both (CPU)|image relRMSE (in-band)|10/0/0|-0.0695|0.001953|improves|
|pedestal32|DC none -> both (CPU)|border rel.RMS|10/0/0|-1.21|0.001953|improves|
|pedestal32|DC none -> both (CUDA)|field RMS|10/0/0|-1.44|0.001953|improves|
|pedestal32|DC none -> both (CUDA)|image transfer (in-band)|10/0/0|-0.0612|0.001953|improves|
|pedestal32|DC none -> both (CUDA)|image relRMSE (in-band)|10/0/0|-0.0734|0.001953|improves|
|pedestal32|DC none -> both (CUDA)|border rel.RMS|10/0/0|-1.21|0.001953|improves|
|pedestal32|CPU -> CUDA (DC none)|field RMS|7/3/0|-0.202|0.3438|neutral/mixed|
|pedestal32|CPU -> CUDA (DC none)|image transfer (in-band)|8/2/0|-0.018|0.1094|neutral/mixed|
|pedestal32|CPU -> CUDA (DC none)|image relRMSE (in-band)|6/4/0|-0.00241|0.7539|neutral/mixed|
|pedestal32|CPU -> CUDA (DC none)|border rel.RMS|8/2/0|-0.00351|0.1094|neutral/mixed|
|pedestal32|CPU -> CUDA (DC both)|field RMS|7/3/0|-5.34e-06|0.3438|neutral/mixed|
|pedestal32|CPU -> CUDA (DC both)|image transfer (in-band)|2/8/0|2.71e-07|0.1094|neutral/mixed|
|pedestal32|CPU -> CUDA (DC both)|image relRMSE (in-band)|7/3/0|-1.49e-07|0.3438|neutral/mixed|
|pedestal32|CPU -> CUDA (DC both)|border rel.RMS|7/3/0|-3.68e-06|0.3438|neutral/mixed|
|contrast025|DC none -> both (CPU)|field RMS|9/1/0|-0.0101|0.02148|improves|
|contrast025|DC none -> both (CPU)|image transfer (in-band)|7/3/0|-8.13e-05|0.3438|neutral/mixed|
|contrast025|DC none -> both (CPU)|image relRMSE (in-band)|4/6/0|0.000206|0.7539|neutral/mixed|
|contrast025|DC none -> both (CPU)|border rel.RMS|2/8/0|0.00174|0.1094|neutral/mixed|
|contrast025|DC none -> both (CUDA)|field RMS|4/6/0|0.00203|0.7539|neutral/mixed|
|contrast025|DC none -> both (CUDA)|image transfer (in-band)|7/3/0|-0.000216|0.3438|neutral/mixed|
|contrast025|DC none -> both (CUDA)|image relRMSE (in-band)|5/5/0|0.000261|1|neutral/mixed|
|contrast025|DC none -> both (CUDA)|border rel.RMS|3/7/0|0.00321|0.3438|neutral/mixed|
|contrast025|CPU -> CUDA (DC none)|field RMS|9/1/0|-0.0116|0.02148|improves|
|contrast025|CPU -> CUDA (DC none)|image transfer (in-band)|7/3/0|-9.93e-05|0.3438|neutral/mixed|
|contrast025|CPU -> CUDA (DC none)|image relRMSE (in-band)|3/7/0|0.000343|0.3438|neutral/mixed|
|contrast025|CPU -> CUDA (DC none)|border rel.RMS|5/5/0|-0.00148|1|neutral/mixed|
|contrast025|CPU -> CUDA (DC both)|field RMS|8/2/0|-4.74e-07|0.1094|neutral/mixed|
|contrast025|CPU -> CUDA (DC both)|image transfer (in-band)|2/8/0|3.18e-07|0.1094|neutral/mixed|
|contrast025|CPU -> CUDA (DC both)|image relRMSE (in-band)|9/1/0|-1.8e-07|0.02148|improves|
|contrast025|CPU -> CUDA (DC both)|border rel.RMS|6/4/0|-6.28e-07|0.7539|neutral/mixed|
|contrast4|DC none -> both (CPU)|field RMS|6/4/0|-2.11e-05|0.7539|neutral/mixed|
|contrast4|DC none -> both (CPU)|image transfer (in-band)|4/6/0|7.79e-07|0.7539|neutral/mixed|
|contrast4|DC none -> both (CPU)|image relRMSE (in-band)|7/3/0|-1.33e-06|0.3438|neutral/mixed|
|contrast4|DC none -> both (CPU)|border rel.RMS|3/7/0|1.1e-05|0.3438|neutral/mixed|
|contrast4|DC none -> both (CUDA)|field RMS|5/5/0|3.73e-06|1|neutral/mixed|
|contrast4|DC none -> both (CUDA)|image transfer (in-band)|7/3/0|-9.56e-07|0.3438|neutral/mixed|
|contrast4|DC none -> both (CUDA)|image relRMSE (in-band)|2/8/0|2.24e-06|0.1094|neutral/mixed|
|contrast4|DC none -> both (CUDA)|border rel.RMS|5/5/0|-1.18e-06|1|neutral/mixed|
|contrast4|CPU -> CUDA (DC none)|field RMS|5/5/0|1.01e-06|1|neutral/mixed|
|contrast4|CPU -> CUDA (DC none)|image transfer (in-band)|1/9/0|1.73e-06|0.02148|harms|
|contrast4|CPU -> CUDA (DC none)|image relRMSE (in-band)|8/2/0|-6.05e-06|0.1094|neutral/mixed|
|contrast4|CPU -> CUDA (DC none)|border rel.RMS|2/8/0|1.51e-05|0.1094|neutral/mixed|
|contrast4|CPU -> CUDA (DC both)|field RMS|5/5/0|-1.94e-08|1|neutral/mixed|
|contrast4|CPU -> CUDA (DC both)|image transfer (in-band)|2/8/0|2.86e-07|0.1094|neutral/mixed|
|contrast4|CPU -> CUDA (DC both)|image relRMSE (in-band)|9/1/0|-1.9e-07|0.02148|improves|
|contrast4|CPU -> CUDA (DC both)|border rel.RMS|9/1/0|-8.5e-07|0.02148|improves|

### Field RMS versus #269 published (afba50a4-equivalent diag build; same movies)

|Arm|pairs|max abs diff px|median abs diff px|bit-equal pairs|
|---|---:|---:|---:|---:|
|cpu-none|100|3.52e-07|6.25e-08|0|
|cpu-both|100|4.02e-07|7.67e-08|0|
|cuda-none|100|4.85e-07|8.89e-08|0|
|cuda-both|100|2.98e-07|9.87e-08|0|
|cpu-double|10|1.87e-07|7.86e-08|0|
