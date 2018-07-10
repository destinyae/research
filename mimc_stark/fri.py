from better_lagrange import lagrange_interp_4, eval_poly_at
from merkle_tree import merkelize, mk_branch, verify_branch
from utils import get_power_cycle, get_pseudorandom_indices
from fft import fft

# Generate an FRI proof
def prove_low_degree(poly, root_of_unity, values, maxdeg_plus_1, modulus):
    print('Proving %d values are degree <= %d' % (len(values), maxdeg_plus_1))

    # If the degree we are checking for is less than or equal to 32,
    # use the polynomial directly as a proof
    if maxdeg_plus_1 <= 32:
        print('Produced FRI proof')
        return [[x.to_bytes(32, 'big') for x in values]]

    # Calculate the set of x coordinates
    xs = get_power_cycle(root_of_unity, modulus)
    assert len(values) == len(xs)

    # Put the values into a Merkle tree. This is the root that the
    # proof will be checked against
    m = merkelize(values)

    # Select a pseudo-random x coordinate
    special_x = int.from_bytes(m[1], 'big') % modulus

    # Calculate the "column" (see https://vitalik.ca/general/2017/11/22/starks_part_2.html)
    # at that x coordinate
    # We calculate the column by Lagrange-interpolating the row, and not
    # directly, as this is more efficient
    column = []
    for i in range(len(xs)//4):
        x_poly = lagrange_interp_4(
            [values[i+len(values)*j//4] for j in range(4)],
            [xs[i+len(xs)*j//4] for j in range(4)],
            modulus
        )
        column.append(eval_poly_at(x_poly, special_x, modulus))
    m2 = merkelize(column)

    # Pseudo-randomly select y indices to sample
    ys = get_pseudorandom_indices(m2[1], len(column), 40)

    # Compute the Merkle branches for the values in the polynomial and the column
    branches = []
    for y in ys:
        branches.append([mk_branch(m2, y)] + [mk_branch(m, y + (len(xs) // 4) * j) for j in range(4)])

    # This component of the proof
    o = [m2[1], branches]

    # In the next iteration of the proof, we'll work with smaller roots of unity
    sub_xs = [xs[i] for i in range(0, len(xs), 4)]

    # Interpolate the polynomial for the column
    ypoly = fft(column[:len(sub_xs)], modulus,
                pow(root_of_unity, 4, modulus), inv=True)

    # Recurse...
    return [o] + prove_low_degree(ypoly, pow(root_of_unity, 4, modulus), column, maxdeg_plus_1 // 4, modulus)

# Verify an FRI proof
def verify_low_degree_proof(merkle_root, root_of_unity, proof, maxdeg_plus_1, modulus):

    # Calculate which root of unity we're working with
    testval = root_of_unity
    roudeg = 1
    while testval != 1:
        roudeg *= 2
        testval = (testval * testval) % modulus

    quartic_roots_of_unity = [1,
                              pow(root_of_unity, roudeg // 4, modulus),
                              pow(root_of_unity, roudeg // 2, modulus),
                              pow(root_of_unity, roudeg * 3 // 4, modulus)]

    # Verify the recursive components of the proof
    for prf in proof[:-1]:
        root2, branches = prf
        print('Verifying degree <= %d' % maxdeg_plus_1)

        # Calculate the pseudo-random x coordinate
        special_x = int.from_bytes(merkle_root, 'big') % modulus

        # Calculate the pseudo-randomly sampled y indices
        ys = get_pseudorandom_indices(root2, roudeg // 4, 40)


        # Verify for each selected y coordinate that the four points from the polynomial
        # and the one point from the column that are on that y coordinate are on the same
        # deg < 4 polynomial
        for i, y in enumerate(ys):
            # The x coordinates from the polynomial
            x1 = pow(root_of_unity, y, modulus)
            xcoords = [(quartic_roots_of_unity[j] * x1) % modulus for j in range(4)]

            # The values from the polynomial
            row = [verify_branch(merkle_root, y + (roudeg // 4) * j, prf) for j, prf in zip(range(4), branches[i][1:])]

            # Verify proof and recover the column value
            values = [verify_branch(root2, y, branches[i][0])] + row

            # Lagrange interpolate and check deg is < 4
            p = lagrange_interp_4(row, xcoords, modulus)
            assert eval_poly_at(p, special_x, modulus) == verify_branch(root2, y, branches[i][0])

        # Update constants to check the next proof
        merkle_root = root2
        root_of_unity = pow(root_of_unity, 4, modulus)
        maxdeg_plus_1 //= 4
        roudeg //= 4

    # Verify the direct components of the proof
    data = [int.from_bytes(x, 'big') for x in proof[-1]]
    print('Verifying degree <= %d' % maxdeg_plus_1)
    assert maxdeg_plus_1 <= 32

    # Check the Merkle root matches up
    mtree = merkelize(data)
    assert mtree[1] == merkle_root

    # Check the degree of the data
    poly = fft(data, modulus, root_of_unity, inv=True)
    for i in range(maxdeg_plus_1, len(poly)):
        assert poly[i] == 0

    print('FRI proof verified')
    return True
