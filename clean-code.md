# Clean Code Principles (by "Uncle Bob" Robert C. Martin)

The core idea of Clean Code is that your code should be simple, direct, and readable. It should look as if it was written by someone who cares deeply about the craft. The ultimate goal is to build a highly maintainable and agile codebase.

---

### 1. Meaningful Naming

* **Intention-Revealing:** Choose names that state intent. If a variable or function needs an explanatory comment, the name is not doing its job.
* **Pronounceable:** Use words you can easily say during team discussions.
* **Searchable:** Use long, meaningful names for constants rather than easily-overlooked "magic numbers" or single letters.
* **No Disinformation:** Avoid names that obscure the actual type or purpose (e.g., don't use `accountList` unless it is strictly a `List`).

### 2. Function Rules

* **Small:** Functions should be very short, ideally taking up only a few lines.
* **Single Responsibility:** Functions should do exactly one thing, do it well, and do it only.
* **Fewer Arguments:** The ideal number of arguments for a function is zero (niladic), followed by one (monadic), then two (dyadic). Avoid three or more.
* **No Side Effects:** A function must not make hidden changes (like unexpectedly modifying a global variable or object state).

### 3. Smart Commenting

* **Explain with Code:** Code should be self-explanatory. Instead of writing a comment, refactor the code so it reads clearly.
* **Avoid Noise/Redundancy:** Do not write comments that simply restate the obvious.
* **Don't Comment Out Code:** Delete unused code instead of commenting it out. Version control exists to bring it back if needed.

### 4. Code Organization & Formatting

* **Vertical Openness:** Separate concepts with blank lines to define logical sections in your code.
* **Vertical Density:** Highly related code and dependent functions should appear close together vertically.
* **Declare Variables Locally:** Variables should be declared as close to their usage as possible.

### 5. Objects vs. Data Structures

* **Hide Internals:** Objects expose behavior and hide internal data. This makes it easy to add new object types without changing existing behavior.
* **Expose Data:** Data structures expose data and have no significant behavior. This makes it easy to add new behaviors without changing existing structures.

### 6. The Boy Scout Rule

* **Leave it cleaner than you found it:** Always check in your code a little cleaner than it was when you checked it out to prevent the codebase from degrading over time.
