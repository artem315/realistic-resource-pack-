// Every gbuffers_* program.  The wrapper file defines one of:
//   GB_TERRAIN GB_BLOCK GB_ENTITIES GB_HAND        opaque, labPBR, forward lit
//   GB_WATER GB_HAND_WATER                         translucent, labPBR, forward lit
//   GB_PARTICLES GB_WEATHER GB_EMISSIVE GB_GLINT GB_DAMAGED GB_BASIC
// and VERTEX or FRAGMENT.

#include "/lib/settings.glsl"
#include "/lib/uniforms.glsl"
#include "/lib/util.glsl"
#include "/lib/sky.glsl"
#include "/lib/shadows.glsl"
#include "/lib/pbr.glsl"
#include "/lib/waving.glsl"
#include "/lib/water.glsl"

#if defined GB_TERRAIN || defined GB_BLOCK || defined GB_ENTITIES || defined GB_HAND
    #define GB_OPAQUE
#endif
#if defined GB_OPAQUE || defined GB_WATER || defined GB_HAND_WATER
    #define GB_PBR
#endif

// ===========================================================================
#ifdef VERTEX

in vec4 mc_Entity;
in vec4 mc_midTexCoord;
in vec4 at_tangent;

out vec2 texcoord;
out vec2 lmcoord;
out vec4 glcolor;
out vec3 viewPos;
out vec3 worldPos;
out vec3 normalV;
out vec4 tangentV;
out vec4 tileBounds;
flat out int blockId;

void main() {
    texcoord = (gl_TextureMatrix[0] * gl_MultiTexCoord0).xy;
    lmcoord = remapLightmap((gl_TextureMatrix[1] * gl_MultiTexCoord1).xy);
    glcolor = gl_Color;
    normalV = normalize(gl_NormalMatrix * gl_Normal);
    tangentV = vec4(normalize(gl_NormalMatrix * at_tangent.xyz), at_tangent.w < 0.0 ? -1.0 : 1.0);
    blockId = int(mc_Entity.x + 0.5);

    vec2 mid = mc_midTexCoord.xy;
    vec2 halfSize = abs(texcoord - mid);
    tileBounds = vec4(mid - halfSize, max(halfSize * 2.0, vec2(1e-6)));

    vec4 vp = gl_ModelViewMatrix * gl_Vertex;
    vec3 playerPos = (gbufferModelViewInverse * vp).xyz;
#ifdef GB_TERRAIN
    playerPos += waveOffset(playerPos + cameraPosition, blockId, texcoord.y < mid.y);
#endif
    worldPos = playerPos + cameraPosition;
    viewPos = (gbufferModelView * vec4(playerPos, 1.0)).xyz;
#if defined GB_HAND || defined GB_HAND_WATER
    // the hand uses its own projection: keep vanilla transform
    viewPos = vp.xyz;
    gl_Position = gl_ProjectionMatrix * vp;
#else
    gl_Position = gl_ProjectionMatrix * vec4(viewPos, 1.0);
#endif
}

#endif
// ===========================================================================
#ifdef FRAGMENT

in vec2 texcoord;
in vec2 lmcoord;
in vec4 glcolor;
in vec3 viewPos;
in vec3 worldPos;
in vec3 normalV;
in vec4 tangentV;
in vec4 tileBounds;
flat in int blockId;

#if defined GB_OPAQUE
layout(location = 0) out vec4 outColor;
layout(location = 1) out vec4 outNormal;   // colortex1: normal (oct), lightmap
layout(location = 2) out vec4 outSpec;     // colortex2: smoothness, f0
layout(location = 3) out vec4 outAlbedo;   // colortex3: albedo, material id
#elif defined GB_WATER || defined GB_HAND_WATER
layout(location = 0) out vec4 outColor;
layout(location = 1) out vec4 outWater;    // colortex6: water normal, mask, skylight
#else
layout(location = 0) out vec4 outColor;
#endif

// ---------------------------------------------------------------- parallax
#if defined GB_TERRAIN && defined POM && defined NORMAL_MAPPING
vec2 atlasUV(vec2 local) { return fract(local) * tileBounds.zw + tileBounds.xy; }

float heightAt(vec2 local, vec2 dx, vec2 dy) {
    return textureGrad(normals, atlasUV(local), dx, dy).a;
}

vec2 parallax(vec2 uv, mat3 tbn, vec2 dx, vec2 dy, out float pomShadow, out bool applied) {
    pomShadow = 1.0;
    applied = false;
    float dist = length(viewPos);
    if (dist > POM_DISTANCE) return uv;
    vec2 local = (uv - tileBounds.xy) / tileBounds.zw;
    float h0 = heightAt(local, dx, dy);
    if (h0 > 0.998) {
        // flat texel: we may still be next to a hole, but skip for speed
        if (textureGrad(normals, uv, dx * 8.0, dy * 8.0).a > 0.998) return uv;
    }
    vec3 v = normalize(viewPos * tbn);          // tangent space, z < 0 into the surface
    float fade = 1.0 - smoothstep(POM_DISTANCE * 0.7, POM_DISTANCE, dist);
    vec2 delta = v.xy / max(-v.z, 0.08) * POM_DEPTH * fade;
    int steps = POM_STEPS;
    float layer = 1.0 / float(steps);
    vec2 stepUV = delta * layer;

    float rayDepth = 0.0;
    float surfDepth = 1.0 - h0;
    vec2 p = local;
    for (int i = 0; i < steps; i++) {
        if (rayDepth >= surfDepth) break;
        p += stepUV;
        rayDepth += layer;
        surfDepth = 1.0 - heightAt(p, dx, dy);
    }
    // linear refinement between the last two samples
    vec2 prevP = p - stepUV;
    float prevRay = rayDepth - layer;
    float prevSurf = 1.0 - heightAt(prevP, dx, dy);
    float after = surfDepth - rayDepth;
    float before = prevSurf - prevRay;
    float w = after / min(after - before, -1e-5);
    p = mix(p, prevP, clamp(w, 0.0, 1.0));
    rayDepth = mix(rayDepth, prevRay, clamp(w, 0.0, 1.0));
    applied = true;

#ifdef POM_SHADOWS
    vec3 l = normalize(normalize(shadowLightPosition) * tbn);
    if (l.z > 0.0 && rayDepth > 0.01) {
        vec2 lStep = l.xy / l.z * POM_DEPTH * fade / 16.0;
        float d = rayDepth;
        vec2 q = p;
        for (int i = 0; i < 16; i++) {
            q += lStep;
            d -= 1.0 / 16.0;
            if (d <= 0.0) break;
            if (1.0 - heightAt(q, dx, dy) < d - 0.02) { pomShadow = 0.0; break; }
        }
    }
#endif
    return atlasUV(p);
}
#endif

// ----------------------------------------------------------------------------
void main() {
    vec2 dx = dFdx(texcoord);
    vec2 dy = dFdy(texcoord);
    float noise = ign(gl_FragCoord.xy);

#if defined GB_BASIC
    outColor = vec4(toLinear(glcolor.rgb), glcolor.a);

#elif defined GB_DAMAGED
    // vanilla multiplies this overlay with the scene
    outColor = texture(gtexture, texcoord) * glcolor;

#elif defined GB_GLINT
    vec4 c = texture(gtexture, texcoord) * glcolor;
    outColor = vec4(toLinear(c.rgb) * 1.5, c.a);

#elif defined GB_EMISSIVE
    vec4 c = texture(gtexture, texcoord) * glcolor;
    if (c.a < 0.01) discard;
    outColor = vec4(toLinear(c.rgb) * 3.0 * EMISSION_STRENGTH, c.a);

#elif defined GB_PARTICLES || defined GB_WEATHER
    vec4 c = texture(gtexture, texcoord) * glcolor;
    if (c.a < 0.02) discard;
    vec3 albedo = toLinear(c.rgb);
    vec3 light = skyAmbientColor() * lmcoord.y * lmcoord.y + blockLightColor(lmcoord.x) + vec3(MIN_LIGHT);
    light += directLightColor() * 0.5 * smoothstep(0.5, 1.0, lmcoord.y);
    #ifdef GB_WEATHER
        // vanilla rain is strongly blue: keep it as faint grey-blue streaks
        albedo = mix(vec3(luma(albedo)), albedo, 0.25) * 1.3;
        c.a *= 0.25;
        light = skyAmbientColor() * 1.2 + directLightColor() * 0.1 + blockLightColor(lmcoord.x);
    #endif
    outColor = vec4(albedo * light, c.a);

#elif defined GB_PBR
    // ---------------------------------------------------------------- PBR path
    vec3 N0 = normalize(normalV);
    vec3 T = normalize(tangentV.xyz - N0 * dot(N0, tangentV.xyz));
    vec3 B = cross(N0, T) * tangentV.w;
    mat3 tbn = mat3(T, B, N0);

    bool isWater = blockId == ID_WATER;
    bool isPlant = blockId == ID_PLANT || blockId == ID_PLANT_UPPER;
    bool isFoliage = isPlant || blockId == ID_LEAVES;

    vec2 uv = texcoord;
    float pomShadow = 1.0;
#if defined GB_TERRAIN && defined POM && defined NORMAL_MAPPING
    if (!isFoliage) {
        bool applied;
        uv = parallax(texcoord, tbn, dx, dy, pomShadow, applied);
    }
#endif

#if defined GB_WATER || defined GB_HAND_WATER
    if (isWater) {
        // water is composited later (refraction, absorption, reflections)
        vec3 nW = waterNormalWorld(worldPos);
        vec3 nV = mat3(gbufferModelView) * nW;
        if (abs(dot(N0, mat3(gbufferModelView)[1])) < 0.5) nV = N0;   // side faces
        if (!gl_FrontFacing) nV = -nV;
        outColor = vec4(0.0);
        outWater = vec4(octEncode(nV), 1.0, lmcoord.y);
        return;
    }
#endif

    vec4 tex = textureGrad(gtexture, uv, dx, dy);
    vec4 albedo;
#if defined GB_TERRAIN
    albedo = vec4(tex.rgb * glcolor.rgb, tex.a);
    float vanillaAO = glcolor.a;
#else
    albedo = tex * glcolor;
    float vanillaAO = 1.0;
#endif
#if defined GB_ENTITIES
    albedo.rgb = mix(albedo.rgb, entityColor.rgb, entityColor.a);
#endif
#if defined GB_OPAQUE
    if (albedo.a < 0.1) discard;
#else
    if (albedo.a < 0.004) discard;
#endif

    // normals
    vec3 N = N0;
    float texAO = 1.0;
#ifdef NORMAL_MAPPING
    vec4 nrm = textureGrad(normals, uv, dx, dy);
    vec2 nxy = nrm.xy * 2.0 - 1.0;
    if (nrm.a > 0.0 || dot(nrm.xyz, nrm.xyz) > 0.0) {
        vec3 nT = vec3(nxy, sqrt(max(1.0 - dot(nxy, nxy), 0.0)));
        N = normalize(tbn * nT);
        texAO = nrm.b;
    }
#endif
    vec3 Nflat = N0;
    if (isPlant) {
        N = normalize(upPosition);
        Nflat = N;
    }
    if (!gl_FrontFacing && !isPlant) {
        N = -N;
        Nflat = -Nflat;
    }

    vec4 spec = textureGrad(specular, uv, dx, dy);
    Material m = decodeMaterial(albedo, spec, texAO * mix(1.0, vanillaAO, 0.85));
    if (blockId == ID_EMISSIVE && m.emission == 0.0) {
        m.emission = smoothstep(0.35, 0.85, luma(albedo.rgb)) * 0.8;
    }
#if defined GB_TERRAIN
    applyWetness(m, worldPos, mat3(gbufferModelViewInverse) * N0, lmcoord.y);
#endif

    int matId = MAT_DEFAULT;
    if (isFoliage) matId = MAT_FOLIAGE;
#if defined GB_ENTITIES || defined GB_BLOCK
    matId = MAT_ENTITY;
#endif
#if defined GB_HAND
    matId = MAT_HAND;
#endif

    vec3 color = shade(m, N, Nflat, viewPos, lmcoord, pomShadow, matId, noise);

#if defined GB_OPAQUE
    outColor = vec4(color, 1.0);
    outNormal = vec4(octEncode(N), lmcoord);
    outSpec = vec4(m.smoothness, m.f0raw / 255.0, 0.0, 1.0);
    outAlbedo = vec4(toSRGB(m.albedo), float(matId) / 255.0);
#else
    // translucent blocks (glass, ice, slime...): add a sky reflection that is not
    // weakened by the alpha blend
    vec3 V = -normalize(viewPos);
    float a = albedo.a;
    if (blockId == ID_ICE) a = max(a, 0.6);
    vec3 F = fresnelSchlick(dot(N, V), max(m.f0, vec3(0.04)));
    vec3 Rw = mat3(gbufferModelViewInverse) * reflect(-V, N);
    vec3 refl = getSky(Rw) * lmcoord.y * lmcoord.y * F * m.smoothness;
    color += refl / max(a, 0.15);
    outColor = vec4(color, a);
    outWater = vec4(0.0);
#endif

#endif
}

#endif
