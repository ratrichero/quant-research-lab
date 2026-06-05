def simulate_equity(trades, capital=10000):
    eq=[capital]
    for t in trades:
        eq.append(eq[-1]*(1+t/100))
    return eq
