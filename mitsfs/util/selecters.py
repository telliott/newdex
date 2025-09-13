from mitsfs import ui


def select_checkout(checkouts, show_members=False):
    width = min(ui.termwidth(), 80) - 1
    print(checkouts.display(width, show_members=show_members, enum=True))
    print(ui.Color.select('Q.'), 'Back to Main Menu')
    print()

    num = ui.readnumber(
        "Select a checkin: ",
        1,
        len(checkouts) + 1,
        escape='Q')

    if num is None:
        return None

    return checkouts[num - 1]
