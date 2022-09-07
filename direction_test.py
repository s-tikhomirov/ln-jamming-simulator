from direction import Direction


def test_direction():
	d_ab = Direction("Alice", "Bob")
	d_ba = Direction("Bob", "Alice")
	d_cd = Direction("Charlie", "Dave")
	assert(d_ab == d_cd)
	assert(d_ab != d_ba)
	assert(d_ab == d_cd == Direction.Alph)
	assert(d_ba == Direction.NonAlph)
	assert(Direction.Alph != Direction.NonAlph)
	assert(str(d_ab) == str(Direction.Alph) == "Alphabetical")
	assert(str(d_ba) == str(Direction.NonAlph) == "NonAlphabetical")
