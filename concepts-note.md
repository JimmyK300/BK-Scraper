You use a variable `x`
│
├── Is the type Copy? (i32, bool, char, simple tuples)
│     └── YES → COPY
│            → x still valid
│            → always compiles
│
└── NO (heap / non-Copy like String, Vec, etc.)
      │
      ├── Are you passing/assigning WITHOUT & ?
      │     └── YES → MOVE
      │            → x becomes INVALID
      │            → using x again = ❌ compile error
      │
      ├── Are you using &x or &mut x ?
      │     └── YES → BORROW
      │            │
      │            ├── &x (immutable borrow)
      │            │     → multiple allowed
      │            │     → no mutation allowed
      │            │
      │            └── &mut x (mutable borrow)
      │                  → ONLY ONE at a time
      │                  → no other borrows exist
      │
      │            → x remains VALID after borrow ends
      │
      └── Are you calling .clone() ?
            └── YES → DEEP COPY
                   → x still valid
                   → expensive

ownership concepts: one own at a time, 1 mutates at a time
it can transfer ownership, borrow and mutable borrow
must be explicit
slice and borrow == references
lifetime: the period during which a reference is valid -> life time gotta update
borrow must not outlive owner same for slice

1. Who owns this?
2. Is it moved, copied, or borrowed?
3. If borrowed:
   - how many?
   - mutable or not?
   - do they overlap?
4. Does any reference outlive the owner?
