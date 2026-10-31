# Walks 64 words with a stride of 4 words (16 B), summing every 4th element.
# Run with --cache to see spatial locality (or the lack of it) in action.
.data
buf:    .space 64
.text
        la   $t0, buf
        li   $t1, 16            # iterations
        li   $t2, 0
loop:   lw   $t3, 0($t0)
        add  $t2, $t2, $t3
        addi $t0, $t0, 16
        addi $t1, $t1, -1
        bne  $t1, $zero, loop
        halt
