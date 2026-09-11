# Debug free-fly camera for greybox validation (no gameplay).
# WASD/QE move, mouse drag looks, wheel adjusts speed. V0 only.
extends Camera3D

var speed := 120.0
var _drag := false

func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_RIGHT:
		_drag = event.pressed
	elif event is InputEventMouseMotion and _drag:
		rotate_y(-event.relative.x * 0.003)
		rotate_object_local(Vector3.RIGHT, -event.relative.y * 0.003)
	elif event is InputEventMouseButton and event.pressed:
		if event.button_index == MOUSE_BUTTON_WHEEL_UP:
			speed = minf(speed * 1.2, 2000.0)
		elif event.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			speed = maxf(speed / 1.2, 5.0)

func _process(delta: float) -> void:
	var dir := Vector3.ZERO
	if Input.is_key_pressed(KEY_W): dir -= transform.basis.z
	if Input.is_key_pressed(KEY_S): dir += transform.basis.z
	if Input.is_key_pressed(KEY_A): dir -= transform.basis.x
	if Input.is_key_pressed(KEY_D): dir += transform.basis.x
	if Input.is_key_pressed(KEY_Q): dir -= transform.basis.y
	if Input.is_key_pressed(KEY_E): dir += transform.basis.y
	if dir != Vector3.ZERO:
		position += dir.normalized() * speed * delta
