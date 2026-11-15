# Methods

How the quiz-return experiments are run: what is modelled, which numbers are
assumed, where they come from, and how the code is checked against the maths.
Every parameter lives in `config/params.yaml`.

---

## 1. What one run is

One run is one simulated class:

1. **Seat the class.** 50 students sit in random seats (they have no fixed seats). 10 of the 60 quizzes belong to absent students.
2. **Shuffle the quizzes.** The stack is a real list of quiz ids in random order.
3. **Give everyone their own speeds.** A walking speed and a searching speed (section 3.3) per student.
4. **Play the class forward** in steps of 0.1 s, following the rules of the method being tested (section 4).
5. **Stop** when every present student either has their quiz or has given up, *and* the leftover quizzes are back with you.

Randomness enters only through the seating, the shuffle, people's speeds and
the small chances described below. Repeating the run many times with different
random draws gives a distribution of outcomes, not a single number (section 6).

---

## 2. The room and how people move

- **Grid.** The floor is divided into 0.4 m × 0.4 m cells, with at most one person per cell. This is the standard cell size of cellular-automaton pedestrian models (Burstedde et al., 2001). Tables, benches and your desk are blocked cells. The layouts come from your sketches and are editable in `config/rooms/*.yaml`.
- **Walking speed.** Each person's free walking speed is drawn from Normal(1.34, 0.26) m/s (Weidmann, 1993), kept between 0.7 and 2.0 m/s, then multiplied by 0.8 for walking between furniture *(assumption)*.
- **Routes.** People take the shortest route between furniture. If someone is in the way they wait, and after 2 s they look for a way round. Two people heading into each other's cell step past each other.
- **Crowds** (only the pile-after-class method). Each person steps to the free neighbouring cell that brings them closest to their goal, with people updated in random order. This is the floor-field model of Burstedde et al. (2001) and Kirchner & Schadschneider (2002).

---

## 3. Finding your own quiz: the probability model

This part decides most of the time in every stack-passing method.

### 3.1 Where is your sheet in the stack?

You are handed a shuffled stack of *n* sheets that includes yours, and you flick through it from the top.

| Sheet you look at | Chance it's yours, if the earlier ones weren't |
|---|---|
| 1st | 1/n |
| 2nd | 1/(n−1) |
| 3rd | 1/(n−2) |
| … | each step more likely, because ruled-out sheets are gone |

Before you start, the chance that your sheet sits at a particular position is the same for every position. For position 3:

(n−1)/n × (n−2)/(n−1) × 1/(n−2) = **1/n**

So your sheet's position *K* is equally likely to be anywhere from 1 to *n* (a uniform distribution); that is exactly what "shuffled" means. On average you check

  **E[K] = (n + 1) / 2** sheets.

The code does not draw *K* from a formula. It shuffles a real list and looks up where your sheet ended up, so the uniform distribution comes from the shuffle itself. Section 7 checks this.

**As the stack shrinks.** When a student takes their sheet out, the remaining sheets are still in random order. The next student therefore faces the same rule with a smaller *n*. In the one-stack method the first student checks about 30 sheets on average, while a student near the end, facing about 11 sheets, checks about 6.

### 3.2 From sheets to seconds

  **Search time = a + b × (sheets checked)**

This is serial self-terminating search: you look at items one by one and stop when you find the target (Treisman & Gelade, 1980; Wolfe, 1998).

| | Meaning | Value | Basis |
|---|---|---|---|
| **a** | setup time: take the stack, start flicking | 3.0 s | assumption |
| **b** | time to check one sheet: read the name, flick | 0.6 s on average | assumption, agreed with the lecturer; reading a short word takes about 0.25 s (Brysbaert, 2019), plus the time to flick paper |

Worked example, one stack of 60:

| | Search time |
|---|---|
| Your sheet on top | 3 + 0.6 × 1 = **3.6 s** |
| Average | 3 + 0.6 × 30.5 = **21.3 s** |
| Your sheet at the bottom | 3 + 0.6 × 60 = **39 s** |

### 3.3 Students differ

Each student gets their own *b*, drawn once from a log-normal distribution with mean 0.6 s and a coefficient of variation of 0.3 *(assumption)*. Human response times are right-skewed: most people are near the typical speed and a few are much slower (Luce, 1986).

### 3.4 Missing your own sheet

- When you reach your sheet, there is a small chance **q = 2 %** that you flick past it *(assumption)*. You then check the rest of the stack without finding it.
- **If you know your sheet must be in this stack** (you are holding every unclaimed sheet), you go through once more. The stack keeps its order, so your sheet is at the same position.
  - Chance of missing it twice: q × q = 0.04 %. Then it ends up with the leftovers.
- **If your sheet might be in another stack,** you make one pass and pass the stack on.
- **On the last stack you haven't seen yet,** you know it must be there, so you get the second pass.

### 3.5 Several stacks: your sheet may not be in the one you get

Suppose the sheets are split at random into *s* equal stacks of *m* (for example 60 into 4 stacks of 15).

| Stack you are handed | Chance yours is in it, if it wasn't in the earlier ones |
|---|---|
| 1st | 15/60 = 25 % |
| 2nd | 15/45 = 33 % |
| 3rd | 15/30 = 50 % |
| 4th | 15/15 = 100 % |

Before you start, each stack is equally likely to be the one (the same reasoning as section 3.1).

- **If yours isn't in a stack,** you check all of it for nothing (3 + 0.6 × 15 = 12 s) and then wait for the next stack.
- **On average** you look through (s + 1)/2 = 2.5 stacks and check

  m × (s − 1)/2 + (m + 1)/2 = 22.5 + 8 = **30.5 sheets**

  This is the same as one big stack. Splitting does **not** reduce how much each person reads. It only helps because several students search at the same time, and it costs waiting for the right stack to arrive.

---

## 4. The methods

Five methods. The code for each is named in brackets.

### Shared by the stack methods (1–3)

- **One stack at a time.** A student holds one stack at a time. A stack that reaches someone who is busy waits in front of them, in the order the stacks arrived.
- **How a student searches** follows section 3. They are *certain* their sheet is in a stack (so a miss earns a second pass) only when it is the last stack they haven't seen.
- **A fixed passing route.** Students are told to pass the stack to the person next to them, so stacks follow a fixed route through the seats (`passing_route` in `quizsim/layout.py`):
  - **G24:** a snake through the rows. The left bank runs front to back, along each row and then into the row behind, ending at the aisle. The stack crosses the aisle once, at the back, and the right bank runs back to front.
  - **E1.17:** round each table. Tables go in a snake: front row left to right, then back row right to left. Each table starts at the seat nearest the previous table and ends at the seat nearest the next one.
  - **Everyone on the route handles the stack.** Someone who already has their quiz just passes it on (2 s).
- **How a hand-over happens:**
  - **On the same bench or table:** always seated, 2 s. The stack slides past empty seats, adding 0.6 s per extra metre *(assumption)*.
  - **To the next row or table:** seated if within 2.5 m (both students lean across). Otherwise the holder gets up, walks it over and walks back.
- **When a stack finishes:**
  - **Nobody further along the route still needs it:** the leftovers are passed forward, seated where possible, towards the student sitting nearest your desk. That student keeps them until every stack has finished, then takes them all up in one trip.
  - **It runs out of sheets:** it simply stops.
- **Teaching time lost** is your time spent walking out, handing stacks over and walking back.

### The six methods

| # | Method | Rules |
|---|---|---|
| 1 | **One stack from one end** `one_stack` | You hand the whole shuffled stack to the first student on the route. It travels the whole route. |
| 2 | **Two stacks from both ends** `two_stacks` | The stack is split at random into 30 + 30. One stack starts at each end of the route and they travel in opposite directions. Both must reach everyone still looking, so they cross in the middle. |
| 3 | **One stack per table** `per_table` | The stack is split at random into one stack per *occupied* table: 8 tables in E1.17, and each half-row of a bench in G24. You walk the route and put a stack at each table. Each stack goes round its table, then on to the next table on the route, handed to whoever there is nearest, and round that table from them. It continues round the whole room until nobody still needs it. |
| 4 | **Calling names, you walk to them** `calling` | You read the next name in the stack: 2 s, plus a 30 % chance of having to repeat it, up to twice *(assumption)*. If the student is absent, there are 4 s of silence and the sheet stays with you. A present student fails to recognise their name with a 2 % chance and ends without their quiz *(assumption)*. Otherwise a hand goes up after 1.5 s and you walk over. In G24 you can't get into the narrow gaps behind the benches. For a student deep in a row, you hand the quiz to the nearest reachable point and it is passed along the bench at 1.5 s per seat, while you move on. The whole return is teaching time lost. |
| 5 | **Pile on my desk, after class** `pile_desk` | Students pack up for 0–20 s, then walk to the desk using the crowd model (section 2). Only people standing right at the desk (the row of spots along its front) can reach the pile, and at most 4 handle it at once. When someone gets a turn, the pile (in its real shuffled order) is spread into 4 chunks. They search the chunks in random order (section 3.5), waiting 3 s for each further chunk *(assumption)*. Everyone else queues behind. Patience is effectively unlimited, because you report that every student present collects theirs: only the absent students' quizzes are left over. People leave by either door. |

(A pile beside the door was also tested: it is the same method in practice, and is no longer compared.)

---

## 5. What is measured

| Metric | Definition |
|---|---|
| **Finish time** | From the start of the method until every present student has their quiz or has given up, and the leftovers are back with you. For method 5 this is time *after* class. |
| **Unclaimed** | Present students who end without their quiz (missed it, or gave up). These quizzes also come back to you. |
| **Teaching time lost** | Your time spent on the return instead of teaching. |
| **Distraction** | Student-minutes spent searching, passing or walking while you are teaching. Methods run after class score 0 here; their cost shows up in finish time and in students' time after class. |
| **Times a student gets up** | Walks a student makes during class to carry a stack to another row or table, or the leftovers to your desk. For the pile, everyone gets up. |
| **Most busy at once** | Peak number of students occupied with the return (searching, handing over, walking) at the same moment. |
| **Privacy exposure** | The number of *other* students' sheets a student looks at, averaged over students. Calling names scores 0 on this, but every name is said aloud. |

---

## 6. Many runs, and how results are reported

- **500 runs** per method and room.
- **Same random draws for every method** in a given run: the same seating, shuffle and speeds. This is called *common random numbers* (Law, 2015). Differences between methods then come from the method, not from luck.
- **Reported:** the **median** (typical class) and the **10th–90th percentile range** (8 classes out of 10 fall inside it).
- **Sensitivity check:** each assumed value (a, b, q, hand-over time, pile access, patience) is varied one at a time, for example halved and doubled, to see whether the ranking of methods changes (Saltelli et al., 2008).

---

## 7. Checking the code against the maths

`tests/test_search_math.py` runs the real search code 200,000 times per check on freshly shuffled stacks and compares the results with the formulas above. It fails if any difference is larger than 4 standard errors.

| Check | Formula | Simulated |
|---|---|---|
| One stack of 60: P(your sheet is on top) | 0.0167 | 0.0163 |
| One stack of 60: P(found within first 10) | 0.1667 | 0.1644 |
| One stack of 60: P(found within first 30) | 0.5000 | 0.4989 |
| One stack of 60: average sheets checked | 30.50 | 30.57 |
| One stack of 60: average search time | 21.30 s | 21.33 s |
| 2 % misses: P(not found after 2 passes) = q² | 0.0004 | 0.0004 |
| 2 % misses: average sheets checked | 31.71 | 31.63 |
| 4 stacks of 15: P(yours is in the 1st stack) | 0.250 | 0.250 |
| 4 stacks of 15: average stacks looked through | 2.50 | 2.50 |
| 4 stacks of 15: average sheets checked | 30.50 | 30.52 |

In addition, all 60 positions come up equally often: chi-square = 63.2, which is below the 99.6 critical value at p = 0.001.

`tests/test_sanity.py` runs every method in both rooms and checks:
- every class finishes;
- every quiz is accounted for (returned + unclaimed = present; leftovers = 60 − returned);
- no two people are ever in the same cell;
- the same seed gives the same seating in every method.

All 6,000 classes of the main experiment finished; none got stuck.

---

## 8. Parameters at a glance

| Parameter | Value | Basis |
|---|---|---|
| Quizzes / students present | 60 / 50 | lecturer |
| Grid cell | 0.4 m | Burstedde et al. (2001) |
| Walking speed | Normal(1.34, 0.26) m/s × 0.8 indoors | Weidmann (1993); indoor factor assumed |
| a, setup time | 3.0 s | assumption |
| b, per sheet | mean 0.6 s, CV 0.3, log-normal | assumption (agreed); Luce (1986) for the shape |
| q, miss chance | 2 % | assumption |
| Passes when the sheet must be there | 2 | assumption |
| Hand-over | 2.0 s; seated on the same bench/table, or within 2.5 m | assumption |
| Sliding past empty seats | +0.6 s per metre beyond 2.5 m | assumption |
| Calling: name / repeat chance / absent silence | 2 s / 30 % (max 2) / 4 s | assumption |
| Calling: not recognised / hand up / pass along bench | 2 % / 1.5 s / 1.5 s per seat | assumption |
| Pile: packing up / people at once / chunk swap | 0–20 s / 4 / 3 s | assumption |
| Pile: patience | effectively unlimited (nobody present leaves without theirs) | lecturer's observation |

All assumed values will be covered by the sensitivity check.

---

## 9. Limitations

- **Not measured in your classroom.** Search speed, misses, hand-over time and patience are estimates. Timing one real stack lap in class would let us calibrate *b*.
- **Students are simplified.** They don't chat, help friends or look at friends' grades.
- **The passing route is idealised.** Real students won't follow it perfectly.
- **Room layouts are from sketches,** not measured plans.

---

## References

- Brysbaert, M. (2019). How many words do we read per minute? A review and meta-analysis of reading rate. *Journal of Memory and Language*, 109, 104047.
- Burstedde, C., Klauck, K., Schadschneider, A. & Zittartz, J. (2001). Simulation of pedestrian dynamics using a two-dimensional cellular automaton. *Physica A*, 295, 507–525.
- Kirchner, A. & Schadschneider, A. (2002). Simulation of evacuation processes using a bionics-inspired cellular automaton model for pedestrian dynamics. *Physica A*, 312, 260–276.
- Law, A. M. (2015). *Simulation Modeling and Analysis* (5th ed.). McGraw-Hill.
- Luce, R. D. (1986). *Response Times: Their Role in Inferring Elementary Mental Organization*. Oxford University Press.
- Saltelli, A. et al. (2008). *Global Sensitivity Analysis: The Primer*. Wiley.
- Treisman, A. M. & Gelade, G. (1980). A feature-integration theory of attention. *Cognitive Psychology*, 12, 97–136.
- Weidmann, U. (1993). *Transporttechnik der Fussgänger*. Schriftenreihe des IVT Nr. 90, ETH Zürich.
- Wolfe, J. M. (1998). What can 1 million trials tell us about visual search? *Psychological Science*, 9(1), 33–39.
