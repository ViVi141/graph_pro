import numpy as np, glob, os
g = r"<ARMA3>"
files = sorted(glob.glob(os.path.join(g, "GP_cb_*_vs0.raw")))
print("files:", len(files))
def find_matrices(v):
    out = []
    for off in range(0, len(v) - 16 + 1, 4):
        m = v[off:off+16].reshape(4, 4)
        # 4x4 affine: last row approx (0,0,0,1)
        if abs(m[3,0]) > 1e-3 or abs(m[3,1]) > 1e-3 or abs(m[3,2]) > 1e-3 or abs(m[3,3]-1) > 1e-3:
            continue
        basis = m[:3, :3]
        lens = np.linalg.norm(basis, axis=0)
        if not all(0.5 < l < 2.0 for l in lens):
            continue
        pos = m[:3, 3]
        if not all(np.isfinite(pos)) or np.max(np.abs(pos)) > 1e5:
            continue
        # orthogonality check on the rotation part
        n = basis / np.maximum(lens, 1e-9)
        dot = np.abs(n.T @ n - np.eye(3)).max()
        if dot < 0.25:
            out.append((off // 4, round(float(lens.mean()), 3), np.round(pos, 2).tolist(), round(float(dot), 3)))
    return out
hits = 0
for f in files[:40]:
    v = np.fromfile(f, dtype=np.float32)
    ms = find_matrices(v)
    if ms:
        hits += 1
        print(os.path.basename(f), "float_off/scale/pos/orth:", ms[:3])
print("files containing an affine 4x4 candidate:", hits, "/", min(40, len(files)))
if files:
    v = np.fromfile(files[0], dtype=np.float32)
    print("\nfirst file, first 16 floats:", np.round(v[:16], 3).tolist())
    print("nonzero floats:", int((np.abs(v) > 1e-6).sum()), "of", v.size)
