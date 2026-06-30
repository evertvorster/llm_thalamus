# Plan: Jealous Husbands Puzzle

## Approach
Write a BFS solver in Python that:
1. Models state as `(left_bank_frozenset, boat_on_left_bool)`
2. Validates each bank independently using the constraint: no wife with another man unless her husband is present
3. Generates all valid 1-person and 2-person boat moves
4. BFS from start to goal, reconstructing the path

## Files
- `/tmp/jealous_husbands_solver.py` — complete solver + inline validator

## Validation
- BFS finds shortest path (11 crossings)
- Each state verified valid by constraint checker
- Path walker re-validates every intermediate state
- Verified solution found, all states valid
