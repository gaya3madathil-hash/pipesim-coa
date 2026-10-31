# A chain of back-to-back RAW (read-after-write) dependencies.
# Expected: t2=12, t3=7, t4=4, t5=7
        li   $t0, 5
        li   $t1, 7
        add  $t2, $t0, $t1
        sub  $t3, $t2, $t0
        and  $t4, $t3, $t2
        or   $t5, $t4, $t3
        halt
