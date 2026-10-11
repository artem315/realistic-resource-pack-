// Screen space ray tracing. Returns xy = hit uv, z = 1 on hit.
vec3 raytrace(vec3 viewPos, vec3 dir, float dither, sampler2D depthTex) {
    float rayLen = (viewPos.z + dir.z * far * 1.7) > -near ? (-near - viewPos.z) / dir.z : far * 1.7;
    vec3 sStart = viewToScreen(viewPos);
    vec3 sEnd = viewToScreen(viewPos + dir * rayLen);
    vec3 sDir = sEnd - sStart;
    // clip the ray to the screen
    vec2 lim = vec2(sDir.x > 0.0 ? (1.0 - sStart.x) / sDir.x : -sStart.x / min(sDir.x, -1e-6),
                    sDir.y > 0.0 ? (1.0 - sStart.y) / sDir.y : -sStart.y / min(sDir.y, -1e-6));
    sDir *= clamp(min(lim.x, lim.y), 0.0, 1.0);

    vec3 prev = sStart;
    for (int i = 1; i <= SSR_STEPS; i++) {
        float t = pow((float(i) - 1.0 + dither) / float(SSR_STEPS), 1.6);
        vec3 p = sStart + sDir * t;
        float d = texture(depthTex, p.xy).r;
        if (p.z > d && d < 1.0) {
            float thick = abs(linearDepth(p.z) - linearDepth(d));
            if (thick < 2.0 + linearDepth(p.z) * 0.1) {
                // binary refine
                vec3 a = prev, b = p;
                for (int j = 0; j < 5; j++) {
                    vec3 m = (a + b) * 0.5;
                    if (m.z > texture(depthTex, m.xy).r) b = m; else a = m;
                }
                return vec3(b.xy, 1.0);
            }
        }
        prev = p;
    }
    return vec3(0.0);
}

float edgeFade(vec2 uv) {
    vec2 e = smoothstep(0.0, 0.08, uv) * smoothstep(1.0, 0.92, uv);
    return e.x * e.y;
}
