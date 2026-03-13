import numbers

def sieve_of_eratosthenes(limit):
    primes = [True] * (limit + 1)
    primes[0] = primes[1] = False
    
    p = 2
    while p * p <= limit:
        if primes[p]:
            for i in range(p, limit + 1, p):
                primes[i] = False
        p += 1
    
    return [i for i in range(2, limit + 1) if primes[i]]

result = sieve_of_eratosthenes(50)
print(f"Prime numbers up to 50: {result}")
print(f"Count: {len(result)}")
