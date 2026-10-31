# Sum an 8-element array and store the result.
# Shows: load-use hazard, loop branch, jump, store.  Expected result: 31
.data
arr:    .word 3, 1, 4, 1, 5, 9, 2, 6
n:      .word 8
result: .word 0

.text
        la   $t0, arr
        la   $t1, n
        lw   $t1, 0($t1)        # t1 = count
        li   $t2, 0             # t2 = sum
loop:   beq  $t1, $zero, done
        lw   $t3, 0($t0)
        add  $t2, $t2, $t3      # load-use hazard on $t3
        addi $t0, $t0, 4
        addi $t1, $t1, -1
        j    loop
done:   la   $t4, result
        sw   $t2, 0($t4)
        halt
