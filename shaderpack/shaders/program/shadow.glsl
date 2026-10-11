#include "/lib/settings.glsl"
#include "/lib/uniforms.glsl"
#include "/lib/util.glsl"
#include "/lib/waving.glsl"
#include "/lib/shadows.glsl"

#ifdef VERTEX
in vec4 mc_Entity;
in vec4 mc_midTexCoord;
out vec2 texcoord;
out vec4 glcolor;
flat out int blockId;

void main() {
    texcoord = (gl_TextureMatrix[0] * gl_MultiTexCoord0).xy;
    glcolor = gl_Color;
    blockId = int(mc_Entity.x + 0.5);
    vec4 vp = gl_ModelViewMatrix * gl_Vertex;
    vec3 playerPos = (shadowModelViewInverse * vp).xyz;
    playerPos += waveOffset(playerPos + cameraPosition, blockId, texcoord.y < mc_midTexCoord.y);
    vec4 clip = gl_ProjectionMatrix * (shadowModelView * vec4(playerPos, 1.0));
    clip.xyz = distortShadow(clip.xyz);
    gl_Position = clip;
}
#endif

#ifdef FRAGMENT
in vec2 texcoord;
in vec4 glcolor;
flat in int blockId;
layout(location = 0) out vec4 outColor;

void main() {
    if (blockId == ID_WATER) discard;   // water does not cast shadows
    vec4 c = texture(gtexture, texcoord) * glcolor;
    if (c.a < 0.1) discard;
    outColor = c;
}
#endif
