# SSB Dev Log — October 14, 2026

## Summary

No code today. I planned the Stage 2 wearable from start to finish: what it
looks like, how it goes on my body, what parts to buy, and the build order.

The big change is the design itself. I dropped the "electronics box on my side
+ cable to a sensor pad" idea and went with one snap-on unit that clicks onto a
heart-rate chest strap. I also updated the plan to match the parts I actually
have, wrote everything up in the team Google Doc, and picked the parts to order.

---

## Design decisions

**1. One snap-on unit instead of a box + cable.**
The cable between the box and the pad would bend every time I breathe or move
my arms, so it would be the first thing to break. Now the electronics and the
sensor pad are one printed piece.

**2. The strap's snaps do two jobs.**
A heart-rate chest strap has two metal snap studs and conductive fabric on the
inside. The unit clicks onto the snaps, and the snaps also carry the GSR signal
from the strap's fabric into the unit. So the strap becomes my GSR electrodes
and the finger straps are retired.

**3. The sensor pad hangs below the strap.**
The strap fabric covers my skin where it crosses my chest, so the MAX30205 and
the vapor chamber sit in a pad below the strap's edge. The pad sticks out
2–3 mm so it presses into my skin.

**4. Nothing stacked.**
The XIAO, GSR board and battery sit side by side in one layer. The battery sits
at strap height, so the strap holds the heaviest part still.
Size: about 70 × 60 × 12 mm, close to a normal heart-rate pod in thickness.
A ~250 mAh battery would make it thinner, but my 500 mAh one works for the first
build.

---

## Updated with the parts I actually have

- MAX30205: ProtoCentral round wearable board. The aluminium back touches skin
  directly and the epoxy top keeps sweat off, so I probably don't need a
  thermal pad.
- SHT45 breakout: 25.5 × 17.7 × 4.8 mm. Too big to sit inside a tiny chamber,
  so the board becomes the chamber floor, with a small cavity over the sensor
  chip (same idea as the Vapor Chamber tab).
- Grove GSR board: listed as 20 × 20 mm (need to check with calipers).
- The pad grew to about 50 × 25 mm to fit both sensors.

---

## Things I learned

- The XIAO has a built-in LiPo charger on its BAT pads, so I don't need the
  TP4056 module.
- On battery alone, the XIAO's 5V pin has no power. Every sensor has to move
  to 3V3. The GSR baseline (~2450) might shift after that, so I'll re-check it.
- The XIAO charges slowly (50 mA, some listings say 100 mA).
- Battery plugs aren't always wired the same way. I have to check + and − with
  a multimeter before soldering, or I could kill the XIAO.

---

## Parts

**Order now:**
- POLAR Soft Strap (M–XXL)
- JST-PH 2.0 pairs with silicone wire
- SS12D00 mini slide switches
- 28 AWG silicone wire
- Heat shrink kit
- Kapton tape

**Later:**
- Snap sockets (after measuring the strap)
- M2 heat-set inserts + screws (Phase 4)
- Epoxy/silicone (before sealing)
- ePTFE membrane (after chamber size is set)
- ~250 mAh battery (only if the unit feels bulky)
- Thermal pad (probably never)

---

## Git

No commits today. Planning and docs only.

---

## Next steps

- Place the parts order.
- Phase 0 (no new parts): clear the test sessions from history, then do a body
  test with the sensors taped under my pecs (rest + short workout).
- When the strap arrives: measure snap spacing, stud size and strap width ->
  order matching snap sockets.
- When the JST kit/switch/wire arrive: battery wiring on the breadboard
  (check polarity -> switch on the + wire -> BAT pads -> sensors to 3V3).
- Settle the vapor chamber size with Callum.
- Update SSB_architecture.md: remove the TP4056, add the strap-mount design.
- Redo the build-stage drawings (today's version was confusing).