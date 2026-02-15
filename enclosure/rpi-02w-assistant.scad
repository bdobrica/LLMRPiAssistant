///////////////////////////////////////////////////////////////
// Raspberry Pi Assistant enclosure
// Houses:
//   Raspberry Pi Zero 2 W
//   ReSpeaker 2-Mics Pi HAT
//   4000mAh AKYGA LP805080 LiPo battery
//   FM5324GA USB-C charger/booster board 5V 2A output
//   40mm 4 Ohm 3W speaker
//   Power button (generic 3-pin slider switch)
//
// Render:
//   assembly("body");        // main body (with studs, speaker guard, wall, latches)
//   assembly("lid");         // back lid
//   assembly("speaker");     // speaker cover
//   assembly("button");      // button cap
//   assembly("all");         // everything (debug)
//
///////////////////////////////////////////////////////////////

/*** PARAMETERS ************************************************/
// Battery
batt_width  = 52.0;
batt_height = 80.0;
batt_depth  = 9.0;

// Speaker
speaker_outer_radius = 25.2;
speaker_inner_radius = 21.5;
speaker_depth        = 22.0;
speaker_top_offset   = 2.0;
speaker_guard_depth  = 5.0;

// RPi
rpi_width        = 65.0 + 2 * 3.5;
rpi_height       = 30.0 + 2 * 1.5;
rpi_depth        = 21.0;
rpi_hole_width   = 58.0;
rpi_hole_height  = 23.0;
rpi_hole_depth   = 5.5;
rpi_hole_offset  = 3.5;
rpi_hole_radius  = 2.45;
rpi_screw_radius = 2.65;

// Mic
mic_width         = 6.0;
mic_height        = 4.0;
mic_corner_radius = 1.0;
mic_guard         = 4.0;

// Button hole (round)
btn_offset_height = 9.0;
btn_offset_width  = 12.5;
btn_guard         = 0;
btn_radius        = 6.0;

// Power button slot (rect)
button_width         = 4.6;
button_height        = 2.6;
button_support_width = 9.0;
button_support_height= 3.9;
button_support_depth = 3.5;
button_stopper_height= 1.6;

// Charger / USB
charger_width          = 21.0;
charger_height         = 25.5;
charger_board_thickness= 2.0;
charger_key_offset     = 13.25;
charger_key_radius     = 1.25;

usb_width  = 9.0;
usb_height = 3.2;
usb_radius = 1.0;

// Wire relief
wire_width  = 5.0;
wire_height = 10.0;
wire_radius = 2.0;

// Shell
wall_thickness = 1.0;
corner_radius  = 2.0;

// Latches
latch_radius        = 0.8;
latch_bottom_offset = 3.0;
latch_side_offset   = 8.0;

// SD slot
sd_card_width        = 13.0;
sd_card_height       = 3.0;
sd_card_bottom_offset= 8.5;
sd_card_face_offset  = 16.5;
sd_card_radius       = 1.0;

// Lid tolerances
lid_offset        = 0.1;
lid_border_height = 4.0;

/*** COMPUTED ***************************************************/
rpi_hole_height_offset = rpi_hole_offset + 1.5;
rpi_hole_width_offset  = rpi_hole_offset + 3.5;

box_height = max(
    2 * speaker_top_offset + 2 * wall_thickness + 2 * speaker_outer_radius +
    3 * wall_thickness + rpi_height,
    batt_height
);
box_depth  = max(rpi_depth, speaker_depth) + batt_depth;
box_width  = rpi_width;

button_face_offset   = (box_depth - button_width) * 0.5;
speaker_latch_offset = speaker_guard_depth * 0.5;
speaker_lid_radius   = speaker_outer_radius + wall_thickness + lid_offset;

/*** RENDER SWITCH *********************************************/
// Change to "body", "lid", "speaker", "button", or "all"
part = "body";

assembly(part);

/*** HELPERS ****************************************************/
module place(v=[0,0,0]) { translate(v) children(); }

module rcube(size, radius=0, center=false) {
    size = (size[0] == undef) ? [size, size, size] : size;
    w = size[0]; d = size[1]; h = size[2];
    tr = center ? [-w/2, -d/2, -h/2] : [0,0,0];

    translate(tr) union() {
        translate([radius, 0, 0]) cube([w - 2*radius, d, h]);
        translate([0, radius, 0]) cube([w, d - 2*radius, h]);

        translate([radius,       radius,       h/2]) cylinder(h=h, r=radius, center=true);
        translate([w-radius,     radius,       h/2]) cylinder(h=h, r=radius, center=true);
        translate([w-radius,     d-radius,     h/2]) cylinder(h=h, r=radius, center=true);
        translate([radius,       d-radius,     h/2]) cylinder(h=h, r=radius, center=true);
    }
}

/*** ANCHORS (single source of truth for long translate vectors) */
function a_speaker_center() =
    [ wall_thickness + speaker_outer_radius + speaker_top_offset,
      wall_thickness + rpi_width * 0.5,
      0 ];

function a_rpi_studs_origin() =
    [ 2 * speaker_top_offset + 2 * speaker_outer_radius + 4 * wall_thickness + rpi_hole_offset + rpi_hole_radius,
      (rpi_width - rpi_hole_width) * 0.5 + wall_thickness,
      0 ];

function a_mic_origin(z=0) =
    [ 2 * speaker_top_offset + 2 * speaker_outer_radius + 4 * wall_thickness
      + rpi_hole_offset + rpi_hole_height - 2 * (rpi_hole_radius + wall_thickness * 0.5),
      (rpi_width - rpi_hole_width - mic_height) * 0.5,
      z ];

function a_btn_round_origin(z=0) =
    [ 2 * speaker_top_offset + 2 * speaker_outer_radius + 4 * wall_thickness
      + rpi_hole_offset + rpi_hole_height + rpi_hole_radius - btn_offset_height,
      rpi_hole_width_offset + wall_thickness + btn_offset_width,
      z ];

function a_power_slot_origin(z=0) =
    [ 2 * speaker_top_offset + 2 * speaker_outer_radius + 3 * wall_thickness
      - (button_support_height + button_height) * 0.5,
      -wall_thickness,
      wall_thickness + button_face_offset + z ];

/*** PART SELECTION *********************************************/
module assembly(which="all") {
    if (which=="all") {
        enclosure_body();
        place([0,0,50]) back_lid();
        speaker_cover();
        place([0,0,-20]) button_cap();
    } else if (which=="body") {
        enclosure_body();
    } else if (which=="lid") {
        back_lid();
    } else if (which=="speaker") {
        speaker_cover();
    } else if (which=="button") {
        button_cap();
    }
}

/*** COMPONENT 1: MAIN BODY *************************************/
module enclosure_body() {
    // Replaced global translate([-wall_thickness,...]) wrapper.
    // Keep it here so all anchors remain identical.
    place([-wall_thickness, -wall_thickness, -wall_thickness]) union() {
        main_shell();
        speaker_guard_with_latches();
        rpi_studs();
        internal_separator_wall();
        power_button_support();
    }

    // External latch beads (front edge)
    body_latches();
}

module main_shell() {
    // This is previous main_body() + its subtractive features.
    difference() {
        union() {
            // outer shell minus inner cavity
            difference() {
                rcube([box_height + 2*wall_thickness, rpi_width + 2*wall_thickness, box_depth + wall_thickness], radius=corner_radius);
                place([wall_thickness, wall_thickness, wall_thickness])
                    rcube([box_height, rpi_width, box_depth + 2*wall_thickness], radius=corner_radius);
            }

            // round button guard boss
            place(a_btn_round_origin(0))
                cylinder(h = btn_guard + wall_thickness, r = btn_radius + wall_thickness);

            // mic guards boss
            place(a_mic_origin(0))
                mic_guards();
        }

        // speaker output
        place([a_speaker_center()[0], a_speaker_center()[1], -wall_thickness])
            cylinder(h = 3*wall_thickness, r = speaker_inner_radius);

        // mic holes
        place(a_mic_origin(-wall_thickness))
            mic_holes();

        // round button hole
        place(a_btn_round_origin(-wall_thickness))
            cylinder(h = btn_guard + 3*wall_thickness, r = btn_radius);

        // charger port (side)
        place([usb_height + 2 * speaker_top_offset + 2 * speaker_outer_radius - charger_board_thickness,
               rpi_width,
               usb_width + (charger_width - usb_width) * 0.5 + wall_thickness])
            rotate([0,90,90]) charger_port();

        // power button slot
        place(a_power_slot_origin(-wall_thickness))
            cube([button_height, 3*wall_thickness, button_width]);

        // sd card slot
        place([box_height - sd_card_bottom_offset - sd_card_width, 2*wall_thickness, sd_card_face_offset])
            rotate([90,0,0]) rcube([sd_card_width, 3*wall_thickness, sd_card_height], radius=sd_card_radius);
    }

    // charger support
    charger_support_bracket();
}

module charger_support_bracket() {
    place([2 * speaker_top_offset + 2 * speaker_outer_radius + wall_thickness,
           rpi_width - charger_height,
           wall_thickness]) {
        cube([charger_board_thickness + wall_thickness, wall_thickness, rpi_depth]);

        place([wall_thickness - charger_board_thickness,
               charger_height + wall_thickness - charger_key_offset,
               0]) {
            difference() {
                rotate([0,90,0])
                    cylinder(h = wall_thickness + charger_board_thickness, r = charger_key_radius);

                place([-wall_thickness, -charger_key_radius, -charger_key_radius - 2*wall_thickness])
                    cube([3*wall_thickness + charger_board_thickness, 2*charger_key_radius, charger_key_radius + wall_thickness]);
            }
        }
    }
}

/*** speaker guard that’s attached to the body (not the cover) */
module speaker_guard_with_latches() {
    place(a_speaker_center()) {
        difference() {
            cylinder(h = speaker_guard_depth + wall_thickness, r = speaker_outer_radius + wall_thickness);
            place([0,0,-wall_thickness])
                cylinder(h = speaker_guard_depth + 3*wall_thickness, r = speaker_outer_radius);
        }

        // latch beads around speaker opening
        place([0,0, wall_thickness + speaker_latch_offset])
            speaker_latch_beads(z=0);
    }
}

/*** studs */
module rpi_studs() {
    place(a_rpi_studs_origin()) {
        rpi_stud();
        place([0, rpi_hole_width, 0])        rpi_stud();
        place([rpi_hole_height, 0, 0])       rpi_stud();
        place([rpi_hole_height, rpi_hole_width, 0]) rpi_stud();
    }
}

module rpi_stud() {
    difference() {
        cylinder(h = rpi_hole_depth + wall_thickness, r = rpi_hole_radius + wall_thickness);
        place([0,0,-wall_thickness])
            cylinder(h = rpi_hole_depth + 3*wall_thickness, r = rpi_hole_radius);

        place([0,0, rpi_hole_depth - wall_thickness])
            cylinder(h = 3*wall_thickness, r = rpi_screw_radius);
    }
}

/*** mic */
module mic_holes() {
    rcube([mic_height, mic_width, mic_guard + 3*wall_thickness], radius=mic_corner_radius);
    place([0, rpi_hole_width, 0])
        rcube([mic_height, mic_width, mic_guard + 3*wall_thickness], radius=mic_corner_radius);
}

module mic_guards() {
    place([-wall_thickness, -wall_thickness, 0]) {
        rcube([mic_height + 2*wall_thickness, mic_width + 2*wall_thickness, wall_thickness + mic_guard], radius=mic_corner_radius);
        place([0, rpi_hole_width, 0])
            rcube([mic_height + 2*wall_thickness, mic_width + 2*wall_thickness, wall_thickness + mic_guard], radius=mic_corner_radius);
    }
}

/*** ports */
module charger_port() {
    rcube([usb_width, usb_height, 3 * wall_thickness], radius=usb_radius);
}

/*** internal separator wall with wire relief */
module internal_separator_wall() {
    place([2 * speaker_top_offset + 2 * speaker_outer_radius + 3 * wall_thickness, 0, 0]) {
        difference() {
            cube([wall_thickness, rpi_width + 2*wall_thickness, rpi_depth + wall_thickness]);

            place([-wall_thickness, rpi_width*0.5 + wall_thickness, rpi_depth*0.5 + wall_thickness])
                rotate([0,90,0])
                    place([-wire_height/2, -wire_width/2, 0])
                        rcube([wire_height, wire_width, 3*wall_thickness], radius=wire_radius);
        }
    }
}

/*** power button support bracket */
module power_button_support() {
    place([2 * speaker_top_offset + 2 * speaker_outer_radius - button_support_height + wall_thickness,
           -wall_thickness,
           -wall_thickness]) {

        cube([button_support_height + 2*wall_thickness,
              button_support_depth + 2*wall_thickness,
              button_face_offset + wall_thickness - (button_support_width - button_width) * 0.5]);

        cube([wall_thickness,
              button_support_depth + 2*wall_thickness,
              rpi_depth + wall_thickness]);

        place([0, 0,
               button_face_offset + wall_thickness - (button_support_width - button_width) * 0.5 + button_support_width])
            cube([2*wall_thickness + button_support_height,
                  button_support_depth + wall_thickness,
                  wall_thickness]);
    }
}

/*** body latches */
module body_latches() {
    place([0, 0, box_depth - latch_bottom_offset]) {
        latch_row(y=0);
        latch_row(y=box_width);
    }
}

module latch_row(y=0) {
    place([latch_side_offset,  y, 0]) sphere(r=latch_radius);
    place([box_height*0.5,     y, 0]) sphere(r=latch_radius);
    place([box_height - latch_side_offset, y, 0]) sphere(r=latch_radius);
}

/*** COMPONENT 2: BACK LID **************************************/
module back_lid() {
    union() {
        rcube([box_height + 2*wall_thickness, rpi_width + 2*wall_thickness, wall_thickness], radius=corner_radius);

        place([wall_thickness + lid_offset, wall_thickness + lid_offset, 0]) {
            difference() {
                rcube([box_height - 2*lid_offset, rpi_width - 2*lid_offset, wall_thickness + batt_depth], radius=corner_radius);

                place([wall_thickness, wall_thickness, -wall_thickness])
                    rcube([box_height - 2*(lid_offset + wall_thickness),
                           rpi_width - 2*(lid_offset + wall_thickness),
                           3*wall_thickness + batt_depth], radius=corner_radius);

                // latch beads that mate with body latches
                union() {
                    place([0, 0, latch_bottom_offset]) {
                        latch_row(y=0);
                        latch_row(y=box_width);
                    }
                }
            }

            // battery pocket
            place([0, wall_thickness + (box_width - batt_width - 2*(wall_thickness + lid_offset)) * 0.5, 0]) {
                difference() {
                    cube([box_height - 2*lid_offset, batt_width, wall_thickness + batt_depth]);
                    place([wall_thickness, wall_thickness, -wall_thickness])
                        cube([box_height - 2*lid_offset - 2*wall_thickness,
                              batt_width - 2*wall_thickness,
                              3*wall_thickness + batt_depth]);
                }
            }
        }
    }
}

/*** COMPONENT 3: SPEAKER COVER *********************************/
module speaker_cover() {
    difference() {
        cylinder(h = speaker_depth, r = speaker_outer_radius + 2*wall_thickness + lid_offset);

        place([0,0,wall_thickness])
            cylinder(h = speaker_depth, r = speaker_outer_radius + wall_thickness + lid_offset);

        // wire relief cutout
        place([speaker_outer_radius + lid_offset, -wire_width/2, speaker_depth - speaker_guard_depth - 2*wall_thickness])
            rotate([0,90,0])
                rcube([wire_height, wire_width, 3*wall_thickness], radius=wire_radius);

        // latch beads that snap onto speaker guard
        place([0,0, speaker_depth - speaker_latch_offset])
            speaker_latch_beads(z=0);
    }
}

module speaker_latch_beads(z=0) {
    rotate([0,0,45]) union() {
        place([-speaker_lid_radius + lid_offset, 0, z]) sphere(r=latch_radius);
        place([0, -speaker_lid_radius + lid_offset, z]) sphere(r=latch_radius);
        place([ speaker_lid_radius - lid_offset, 0, z]) sphere(r=latch_radius);
        place([0,  speaker_lid_radius - lid_offset, z]) sphere(r=latch_radius);
    }
}

/*** COMPONENT 4: BUTTON CAP ************************************/
module button_cap() {
    difference() {
        union() {
            cylinder(h = wall_thickness,      r = btn_radius + wall_thickness);
            cylinder(h = 3.5*wall_thickness,  r = btn_radius - lid_offset);
        }
        place([0,0,-wall_thickness])
            cylinder(h = 2*wall_thickness, r = btn_radius - wall_thickness);
    }
}
