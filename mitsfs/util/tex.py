
def texquote(s):
    s = ''.join(((i in '&$%#_') and ('\\' + i) or i for i in s))
    o = u''
    cjk = False
    for c in s:
        if ord(c) < 0x3000:
            if cjk:
                o += '}'
                cjk = False
        else:
            if not cjk:
                o += r'{\unifont '
                cjk = True
        o += c
    if cjk:
        o += '}'
    return o


def nicetitle(line):
    series = [i.replace(',', r'\,') for i in line.series if i]
    titles = [  # strip the alt titles
        '=' in i and i[:i.find('=')] or i for i in line.titles]
    if series:
        if len(series) == len(titles):
            titles = ['%s [%s]' % i for i in zip(titles, series)]
        elif len(titles) == 1:
            titles = ['%s [%s]' % (titles[0], '|'.join(series))]
        elif len(series) == 1:
            titles = ['%s [%s]' % (i, series[0]) for i in titles]
        else:  # this is apparently Officially Weird
            print('Wacky title/series match: ', str(line))
            ntitles = ['%s [%s]' % i for i in zip(titles, series)]
            if len(line.series) < len(titles):
                ntitles += titles[len(series):]
            titles = ntitles
    return '|'.join(titles)
