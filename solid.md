# The SOLID Principles (by Robert C. Martin)

These five design principles make software designs more understandable, flexible, and maintainable.

---

### 1. Single Responsibility Principle (SRP)

* **Definition:** A class should have one, and only one, reason to change.
* **Core Idea:** Gather together the things that change for the same reasons. Separate things that change for different reasons. This prevents a change in one feature from breaking an unrelated feature.

### 2. Open/Closed Principle (OCP)

* **Definition:** Software entities should be open for extension, but closed for modification.
* **Core Idea:** You should be able to extend the behavior of a system without altering its existing source code. This is usually achieved by using interfaces, abstract classes, and polymorphism.

### 3. Liskov Substitution Principle (LSP)

* **Definition:** Subtypes must be substitutable for their base types.
* **Core Idea:** Derived classes must fulfill the behavior expected by the base class without breaking the application. If a subclass cannot perform the same actions as its parent class, it violates LSP.

### 4. Interface Segregation Principle (ISP)

* **Definition:** Clients should not be forced to depend on methods they do not use.
* **Core Idea:** It is better to have many small, specific interfaces rather than one large, general-purpose interface. This keeps classes lean and avoids forcing them to implement dead code.

### 5. Dependency Inversion Principle (DIP)

* **Definition:** High-level modules should not depend on low-level modules. Both should depend on abstractions. Abstractions should not depend on details. Details should depend on abstractions.
* **Core Idea:** Use interfaces or abstract classes to decouple your code. High-level business logic should never directly depend on low-level implementation details like database drivers or specific API clients.
