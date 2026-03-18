# Smart Sweat-Band (SSB)
**A High-Fidelity Wearable for Post-Exercise Recovery & Hydration Analytics**

**Status:** Phase 1 - Sensor Fusion & Calibration (Awaiting Initial Hardware)

## Overview
The Smart Sweat-Band (SSB) is a wearable diagnostic tool engineered to optimize the 20–30 minute post-exercise "recovery window" for athletes. Moving beyond generic activity tracking, the SSB establishes a personalized baseline using a custom-engineered Vapor Chamber and a multi-sensor array to provide individualized recommendations for hydration and thermal regulation post workout.

## Acknowledgements 
This project is funded by the **Dick and St. Jane Reeve Endowed Fund** at RIT.

## Technical Approach & Innovations
Powered by an **ESP32-S3** microcontroller, the SSB processes three critical physiological data streams:

1. **Vapor Chamber Hygrometry (Primary Innovation):** Solves the liquid sweat saturation problem that causes sensors to fail due to flooding because of large amount of sweat. An SHT45 humidity sensor is housed in a micro-climate chamber separated from the skin by an ePTFE membrane, allowing water vapor to pass while blocking liquid droplets, which prevents flooding.
2. **Clinical-Grade Thermometry:** Utilizes a MAX30205 sensor to track thermal recovery (heat dissipation efficiency) with ±0.1°C accuracy.
3. **Dynamic Galvanic Skin Response (GSR):** Gold-plated electrodes measure skin conductivity trends to identify changes in electrolyte concentration during the period when sweat starts to dry.

## App Integration & Scientific Logic
The hardware data streams to a custom mobile dashboard that generates a dynamic **Recovery Readiness Score** and personalized instructions:

* **Rehydration Prescription:** Provides exact volume and electrolyte ratios. Utilizing the ACSM's 150% fluid replacement rule and calculating the sodium mass balance via `m_Na = ∫ (C_sweat · V_rate) dt`, the app prevents dilutional hyponatremia.
* **Gastric Emptying Rate (GER) Optimization:** The prescription is paced into 15-minute "intake windows" (e.g., 250ml every 15 mins) to prevent GI distress and ensure the body's maximum absorption capacity (~1.2L/hr) is not exceeded.
* **Thermal Regulation Alerts:** Analyzes evaporative cooling and the Second Law of Thermodynamics to suggest immediate interventions (e.g., ice-vest application) if the athlete is in a heat-trapped state.
