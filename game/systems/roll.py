import random


def roll_dice(num_dice, sides):
    total = 0
    for _ in range(num_dice):
        total += roll_die(sides)
    return total


def roll_die(sides):
    """Roll a dice with the given number of sides."""
    return random.randint(1, sides)
