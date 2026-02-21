package purego

func Dlsym(handle uintptr, symbol string) (uintptr, error) {
	_ = handle
	_ = symbol
	return 0, nil
}

func RegisterFunc(target any, symbol uintptr) {
	_ = target
	_ = symbol
}
