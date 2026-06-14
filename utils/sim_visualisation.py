# Function to make main graphics
def sim_visualisation(num_doctors, daily_num_patients,
                      acuity_type, ed_simtype,
                      sdec_Percentage, ambulance_vs_nonambulance_Percentage, ac12_ambulance_Majors_vs_Resus_Percentage,
                      ac12_nonambulanceNonResus_MajorsDirect_Vs_WR_Percentage,
                      a12_nonambulance_resus_vs_non_resus_Percentage,
                      a3_AmbulanceMHPatient_Percentage, a3_NonAmbulance_MHPatient_Percentage,
                      hospitalbedCulture, bedOccupancy, errorTrials, errorCatch, time_end2):

    # Javascript
    var = """
        // Images
        const door = new Image();
        door.src = "static/js/images/door.png";
        const acuity1picture = new Image();
        acuity1picture.src = "static/js/images/redfigure.png";
        const acuity2picture = new Image();
        acuity2picture.src = "static/js/images/orangefigure.png";
        const acuity3picture = new Image();
        acuity3picture.src = "static/js/images/yellowfigure.png";
        const acuity4picture = new Image();
        acuity4picture.src = "static/js/images/greenfigure.png";
        const acuity5picture = new Image();
        acuity5picture.src = "static/js/images/bluefigure.png";
        const hospitalPicture = new Image();
        hospitalPicture.src = "static/js/images/hospital.png";
        const crtpPicture = new Image();
        crtpPicture.src = "static/js/images/crtp.png";
        const xrayctPicture = new Image();
        xrayctPicture.src = "static/js/images/xray_ct.png";
        const logo = new Image();
        logo.src = "static/js/images/DHSCsquare.png";

        //Calculating aspect ratio of logo so it matches the rectangle we have in the display
        const destWidth = 200;
        const destHeight = 96;
        const aspectRatio = logo.width / logo.height
        
        // Calculate the width and height based on the aspect ratio
        let logo_width = destWidth;
        let logo_height = destHeight / aspectRatio;
        
        // Check if the calculated height exceeds the destination height
        if (logo_width > destHeight) {
            logo_width = destHeight;
            logo_width = destHeight * aspectRatio;
        }

        //Add acuity legend
        const acuity_legend = new Image();
        acuity_legend.src = "static/js/images/Acuity_Legend.png";
        
        // Hide header
        function scrollFunction() {
            if (document.body.scrollTop > 10 || document.documentElement.scrollTop > 10) {
                document.getElementById("formHeader").style.top = "-150px";
            } else {
                document.getElementById("formHeader").style.top = "0px";
            }
        }
        window.onscroll = function() {scrollFunction()};

        // Loader
        var loader = document.getElementById("loader");
        var submit = document.getElementById("submit");
        loader.style.display = 'none';

        // Simulation parameter values
        document.getElementById("docNumber").textContent =  'Number\xC2\xA0of\xC2\xA0doctors:\xC2\xA0""" + str(
        num_doctors) + """';
        document.getElementById("patNumber").textContent = 'Number\xC2\xA0of\xC2\xA0patients:\xC2\xA0""" + str(
        daily_num_patients) + """';
        //document.getElementById("acType").textContent = 'Type of ED: """ + str(acuity_type) + """, ';
        //document.getElementById("edType").textContent = 'Size of ED: """ + str(ed_simtype) + """, ';
        //document.getElementById("sdec_Percentage").textContent = 'Require X-Ray: """ + str(sdec_Percentage) + """%';
        //document.getElementById("ambulance_vs_nonambulance_Percentage").textContent = 'Require X-Ray: """ +\
          str(ambulance_vs_nonambulance_Percentage) + """%';
        //document.getElementById("ac12_ambulance_Majors_vs_Resus_Percentage").textContent = 'Require X-Ray: """ +\
          str(ac12_ambulance_Majors_vs_Resus_Percentage) + """%';
        //document.getElementById("ac12_nonambulanceNonResus_MajorsDirect_Vs_WR_Percentage").textContent = 'Require X-Ray: """ +\
          str(ac12_nonambulanceNonResus_MajorsDirect_Vs_WR_Percentage) + """%';
        //document.getElementById("a12_nonambulance_resus_vs_non_resus_Percentage").textContent = 'Require X-Ray: """ +\
          str(a12_nonambulance_resus_vs_non_resus_Percentage) + """%';
        //document.getElementById("a3_AmbulanceMHPatient_Percentage").textContent = 'Require X-Ray: """ +\
          str(a3_AmbulanceMHPatient_Percentage) + """%';
        //document.getElementById("a3_NonAmbulance_MHPatient_Percentage").textContent = 'Require X-Ray: """ +\
          str(a3_NonAmbulance_MHPatient_Percentage) + """%';
       
        // Keep selected option
        function dropdownSelects(dropdownId, selectedOption) {
            var dropdown = document.getElementById(dropdownId);
            for(var i, j = 0; i = dropdown.options[j]; j++) {
                if(i.value == selectedOption) {
                    dropdown.selectedIndex = j;
                    break;
                }
            }
        };

        // Drop down selects
        dropdownSelects("acTypeid", \"""" + acuity_type + """\");
        dropdownSelects("edTypeid", \"""" + ed_simtype + """\");
        dropdownSelects("hospitalbedCultureid", \"""" + hospitalbedCulture + """\");
        dropdownSelects("bedOccupancyid", \"""" + bedOccupancy + """\");

        // Alerts for potential problems
        if (\"""" + errorTrials + """\" == "yes") { window.alert("Please resubmit");}
        else if (\"""" + errorCatch + """\" == "ValueError") { window.alert("Invalid values. Please check config file and resubmit");}
        else if (\"""" + errorCatch + """\" == "OtherError") { window.alert("Something went wrong. Please check config file and resubmit");}

        const goButton = document.getElementById("goButton");
        const pdfButton = document.getElementById("pdfButton");
        const aboutButton = document.getElementById("aboutButton");

        aboutButton.innerHTML = '<img style="width:auto;height:30px;" src="static/js/images/AboutEDSim.svg" />';
        pdfButton.innerHTML = '<img style="width:auto;height:30px;" src="static/js/images/ProducePDF.svg" />';

        const IMAGE_WIDTH = 25;
        const IMAGE_HEIGHT = 25;
        const WAITING_ROOM_WIDTH = 0;
        const TREATMENT_WIDTH = 0;
        const XRAYCT_WIDTH = 0;
        var now = 0
        
        // Events always take place in this order
        const EventTypeWeight = {
            ARRIVE_AT_ED: 0,
            GO_TO_WAITING_ROOM: 1,
            TAKE_A_SEAT: 2,
            WAIT_IN_WAITING_ROOM: 3,
            GO_TO_TREATMENT_ROOM: 4,
            GET_TREATMENT: 5,
            GO_TO_XRAYCT: 7,
            PERFORM_XRAYCT: 8,
            GO_TO_MAJORS: 9,
            GET_TREATMENT_MAJORS: 10,
            GO_TO_RESUS: 11,
            GET_TREATMENT_RESUS: 12,
            GO_TO_SDEC: 13,
            GET_TREATMENT_SDEC: 14,
            GO_TO_CRTP: 15,
            IN_CRTP: 16,
            CAPACITY: 100,
            GO_TO_HOSPITAL: 900,
            HOSPITAL_LEAVE: 901,
            GO_TO_EXIT: 1000,
            LEAVE: 1001,
        };
        const SortAndInjectSequentialIDs = (events) => {
            events = events.sort((a, b) => (a.time === b.time ? EventTypeWeight[a.event] - EventTypeWeight[b.event] : a.time - b.time));            
            let id = 0;
            return events.map((e) => Object.assign({ id: id++ }, e));
        };
        // -------------------------
        //  CANVAS OBJECTS
        // -------------------------
        class Queue {
            queueType;
            num;
            xy;
            width;
            static DISTANCE = 20;
            waiting = {};
            constructor(queueType, num, xy, width) {
                this.queueType = queueType;
                this.num = num;
                this.xy = xy;
                this.width = width;
            }
            draw(ctx, now) {
                if (this.num == 0){
                    ctx.fillText(`${this.queueType}`, this.xy.x, this.xy.y);
                }
                else {
                    ctx.fillText(`${this.queueType} #${this.num}`, this.xy.x, this.xy.y);
                }
            }
            registerPeople(people, peopleInLine) {
                this.waiting[people.sort().join(",")] = peopleInLine;
            }
            removePeople(people) {
                delete this.waiting[people.sort().join(",")];
            }
            peopleWaiting(now) {
                return Object.keys(this.waiting).filter((k) => this.waiting[k].end < now);
            }
            positionFromFrontOfLine(now, people) {
                const keys = Object.keys(this.waiting).filter((k) => this.waiting[k].end < now);
                const ordered = keys.sort((a, b) => this.waiting[b].end - this.waiting[a].end);
                return ordered.length - ordered.indexOf(people.sort().join(","));
            }
            queueBegin(now) {
                const keys = Object.keys(this.waiting).filter((k) => this.waiting[k].end < now);
                return { x: this.xy.x - 5 - keys.length * this.width - this.width, y: this.xy.y };
            }
            get queueTerminus() {
                return { x: this.xy.x - 5, y: this.xy.y };
            }
            get serviceLocation() {
                return { x: this.xy.x + 5, y: this.xy.y };
            }
        }
        class Person {
            id;
            acuity;
            waitingForED;
            waitingRoomSeats;
            treatmentRooms;
            majorRooms;
            resusRooms;
            sdecRooms;
            xRayCT;
            CRTP;
            hospital;
            exit;
            static START_AT = { x: 100, y: 300 };
            static GROUP_SPACING = 6;
            events = [];
            msEvents = [];
            picture = new Image();
            positionInGroup = 0;
            lastWalkingStart = { x: Person.START_AT.x, y: Person.START_AT.y };
            constructor(id, acuity, waitingForED, waitingRoomSeats, treatmentRooms, majorRooms, resusRooms, sdecRooms, 
            xRayCT, CRTP, hospital, exit) {
                this.id = id;
                this.acuity = acuity;
                this.waitingForED = waitingForED;
                this.waitingRoomSeats = waitingRoomSeats;
                this.treatmentRooms = treatmentRooms;
                this.majorRooms = majorRooms;
                this.resusRooms = resusRooms;
                this.sdecRooms = sdecRooms;
                this.xRayCT = xRayCT;
                this.CRTP = CRTP;
                this.hospital = hospital;
                this.exit = exit;
            }
            getpicture(acuity) {
                if (acuity == "acuity 1"){
                    this.picture = acuity1picture;
                }
                else if (acuity == "acuity 2"){
                    this.picture = acuity2picture;
                }
                else if (acuity == "acuity 3"){
                    this.picture = acuity3picture;
                }
                else if (acuity == "acuity 4"){
                    this.picture = acuity4picture;
                }
                else if (acuity == "acuity 5"){
                    this.picture = acuity5picture;
                }
            }
            registerEvent(event) {
                this.events.push(event);
                if (event.people) {
                    this.positionInGroup = event.people.indexOf(this.id);
                }
            }
            draw(ctx, now) {
                const topEvent = this.events[this.events.length - 1];
                if (!topEvent || topEvent.event === "ARRIVE_AT_ED") {
                    ctx.drawImage(door, this.lastWalkingStart.x, this.lastWalkingStart.y, IMAGE_WIDTH, IMAGE_HEIGHT);
                    ctx.drawImage(door, 1500, 500, IMAGE_WIDTH, IMAGE_HEIGHT);
                    ctx.drawImage(crtpPicture, 1350, 300, IMAGE_WIDTH, IMAGE_HEIGHT);
                    ctx.drawImage(hospitalPicture, 1500, 100, IMAGE_WIDTH, IMAGE_HEIGHT);
                    ctx.drawImage(xrayctPicture, 1100, 300, IMAGE_WIDTH, IMAGE_HEIGHT);
                    ctx.drawImage(logo, 10, 10, logo_width, logo_height);
                    ctx.drawImage(acuity_legend, 20, 370, 130, 130);

                    return;
                }
                
                const wabble = Math.random() * 3;
                const queue = (() => {
                    if (topEvent.treatmentRoom) {
                        return this.treatmentRooms[topEvent.treatmentRoom - 1];
                    }
                    else if (topEvent.waitingRoomSeat) {
                        return this.waitingRoomSeats[topEvent.waitingRoomSeat - 1];
                    }
                    else if (topEvent.majorRoom) {
                        return this.majorRooms[topEvent.majorRoom - 1];
                    }
                    else if (topEvent.resusRoom) {
                        return this.resusRooms[topEvent.resusRoom - 1];
                    }
                    else if (topEvent.sdecRoom) {
                        return this.sdecRooms[topEvent.sdecRoom - 1];
                    }
                    else if (topEvent.xRayCT) {
                        return this.xRayCT[topEvent.xRayCT - 1];
                    }
                    else if (topEvent.CRTP) {
                        return this.CRTP[topEvent.CRTP - 1];
                    }
                    else if (topEvent.hospital) {
                        return this.hospital[topEvent.hospital - 1];
                    }
                    else if (topEvent.exit) {
                        return this.exit[topEvent.exit - 1];
                    }
                    else {
                        console.error("No queue found");
                        throw new Error("Invalid state of affairs.");
                    }
                })();
                this.getpicture(topEvent.acuity)

                switch (topEvent.event) {
                    case "GO_TO_WAITING_ROOM":
                        //console.log("GO_TO_WAITING_ROOM", this.id, topEvent)
                        queue.registerPeople([topEvent.person], { begin: topEvent.time, end: topEvent.time +
                         topEvent.duration });
                        {
                            const durationElapsed = now - topEvent.time;
                            const durationRatio = durationElapsed / topEvent.duration;
                            const start = this.lastWalkingStart;
                            const destination = queue.queueBegin(now);
                            const x = start.x + (destination.x - start.x) * durationRatio + 
                            this.positionInGroup * Person.GROUP_SPACING + wabble;
                            const y = start.y + (destination.y - start.y) * durationRatio + wabble;
                            ctx.drawImage(this.picture, x, y, IMAGE_WIDTH, IMAGE_HEIGHT);
                        }
                        break;
                    case "WAIT_IN_WAITING_ROOM":
                        //console.log("WAIT_IN_WAITING_ROOM", this.id, topEvent)
                        queue.removePeople([topEvent.person]);
                        {
                            const seqNo = [topEvent.person].indexOf(this.id);
                            const serviceLocation = queue.serviceLocation;
                            this.lastWalkingStart = serviceLocation;
                            ctx.drawImage(this.picture, serviceLocation.x + seqNo * Person.GROUP_SPACING, 
                            serviceLocation.y, IMAGE_WIDTH, IMAGE_HEIGHT);
                        }
                        break;
                    case "GO_TO_TREATMENT_ROOM":
                        queue.registerPeople([topEvent.person], { begin: topEvent.time, end: topEvent.time +
                         topEvent.duration });
                        {
                            const durationElapsed = now - topEvent.time;
                            const durationRatio = durationElapsed / topEvent.duration;
                            const start = this.lastWalkingStart;
                            const destination = queue.queueBegin(now);
                            const x = start.x + (destination.x - start.x) * durationRatio +
                             this.positionInGroup * Person.GROUP_SPACING + wabble;
                            const y = start.y + (destination.y - start.y) * durationRatio + wabble;
                            ctx.drawImage(this.picture, x, y, IMAGE_WIDTH, IMAGE_HEIGHT);
                        }
                        break;
                    case "GET_TREATMENT":
                        {
                            const seqNo = [topEvent.people].indexOf(this.id);
                            const serviceLocation = queue.serviceLocation;
                            this.lastWalkingStart = serviceLocation;
                            ctx.drawImage(this.picture, serviceLocation.x + seqNo * Person.GROUP_SPACING, 
                            serviceLocation.y, IMAGE_WIDTH, IMAGE_HEIGHT);
                        }
                        break;
                    case "GO_TO_MAJORS":
                        queue.registerPeople([topEvent.person], { begin: topEvent.time, end: topEvent.time +
                         topEvent.duration });
                        {
                            const durationElapsed = now - topEvent.time;
                            const durationRatio = durationElapsed / topEvent.duration;
                            const start = this.lastWalkingStart;
                            const destination = queue.queueBegin(now);
                            const x = start.x + (destination.x - start.x) * durationRatio +
                             this.positionInGroup * Person.GROUP_SPACING + wabble;
                            const y = start.y + (destination.y - start.y) * durationRatio + wabble;
                            ctx.drawImage(this.picture, x, y, IMAGE_WIDTH, IMAGE_HEIGHT);
                        }
                        break;
                    case "GET_TREATMENT_MAJORS":
                        {
                            const seqNo = [topEvent.people].indexOf(this.id);
                            const serviceLocation = queue.serviceLocation;
                            this.lastWalkingStart = serviceLocation;
                            ctx.drawImage(this.picture, serviceLocation.x + seqNo * Person.GROUP_SPACING,
                             serviceLocation.y, IMAGE_WIDTH, IMAGE_HEIGHT);
                        }
                        break;
                    case "GO_TO_RESUS":
                        queue.registerPeople([topEvent.person], { begin: topEvent.time, end: topEvent.time +
                         topEvent.duration });
                        {
                            const durationElapsed = now - topEvent.time;
                            const durationRatio = durationElapsed / topEvent.duration;
                            const start = this.lastWalkingStart;
                            const destination = queue.queueBegin(now);
                            const x = start.x + (destination.x - start.x) * durationRatio +
                             this.positionInGroup * Person.GROUP_SPACING + wabble;
                            const y = start.y + (destination.y - start.y) * durationRatio + wabble;
                            ctx.drawImage(this.picture, x, y, IMAGE_WIDTH, IMAGE_HEIGHT);
                        }
                        break;
                    case "GET_TREATMENT_RESUS":
                        {
                            const seqNo = [topEvent.people].indexOf(this.id);
                            const serviceLocation = queue.serviceLocation;
                            this.lastWalkingStart = serviceLocation;
                            ctx.drawImage(this.picture, serviceLocation.x + seqNo * Person.GROUP_SPACING,
                             serviceLocation.y, IMAGE_WIDTH, IMAGE_HEIGHT);
                        }
                        break;
                    case "GO_TO_SDEC":
                        queue.registerPeople([topEvent.person], { begin: topEvent.time, end: topEvent.time +
                         topEvent.duration });
                        {
                            const durationElapsed = now - topEvent.time;
                            const durationRatio = durationElapsed / topEvent.duration;
                            const start = this.lastWalkingStart;
                            const destination = queue.queueBegin(now);
                            const x = start.x + (destination.x - start.x) * durationRatio +
                             this.positionInGroup * Person.GROUP_SPACING + wabble;
                            const y = start.y + (destination.y - start.y) * durationRatio + wabble;
                            ctx.drawImage(this.picture, x, y, IMAGE_WIDTH, IMAGE_HEIGHT);
                        }
                        break;
                    case "GET_TREATMENT_SDEC":
                        {
                            const seqNo = [topEvent.people].indexOf(this.id);
                            const serviceLocation = queue.serviceLocation;
                            this.lastWalkingStart = serviceLocation;
                            ctx.drawImage(this.picture, serviceLocation.x + seqNo * Person.GROUP_SPACING,
                             serviceLocation.y, IMAGE_WIDTH, IMAGE_HEIGHT);
                        }
                        break;
                    case "GO_TO_EXIT":
                        queue.registerPeople([topEvent.person], { begin: topEvent.time, end: topEvent.time +
                         topEvent.duration });
                        {
                            const durationElapsed = now - topEvent.time;
                            const durationRatio = durationElapsed / topEvent.duration;
                            const start = this.lastWalkingStart;
                            const destination = queue.queueBegin(now);
                            const x = start.x + (destination.x - start.x) * durationRatio +
                             this.positionInGroup * Person.GROUP_SPACING + wabble;
                            const y = start.y + (destination.y - start.y) * durationRatio + wabble;
                            ctx.drawImage(this.picture, x, y, IMAGE_WIDTH, IMAGE_HEIGHT);
                        }
                        break;
                    case "LEAVE":
                        queue.removePeople([topEvent.person]);
                        {
                            if (now < topEvent.time + topEvent.duration) {
                                const serviceLocation = queue.serviceLocation;
                            }
                            else {
                                // TODO: Self destruct
                            }
                        }
                        break;
                    case "GO_TO_XRAYCT":
                        queue.registerPeople([topEvent.person], { begin: topEvent.time, end: topEvent.time +
                         topEvent.duration });
                        {
                            const durationElapsed = now - topEvent.time;
                            const durationRatio = durationElapsed / topEvent.duration;
                            const start = this.lastWalkingStart;
                            const destination = queue.queueBegin(now);
                            const x = start.x + (destination.x - start.x) * durationRatio + wabble +
                             this.positionInGroup * Person.GROUP_SPACING;
                            const y = start.y + (destination.y - start.y) * durationRatio + wabble;
                            ctx.drawImage(this.picture, x, y, IMAGE_WIDTH, IMAGE_HEIGHT);
                        }
                        break;
                    case "PERFORM_XRAYCT":
                        {
                            const seqNo = [topEvent.people].indexOf(this.id);
                            const serviceLocation = queue.serviceLocation;
                            this.lastWalkingStart = serviceLocation;
                            ctx.drawImage(this.picture, serviceLocation.x + seqNo * Person.GROUP_SPACING,
                             serviceLocation.y, IMAGE_WIDTH, IMAGE_HEIGHT);
                        }
                        break;
                    case "GO_TO_CRTP":
                        queue.registerPeople([topEvent.person], { begin: topEvent.time, end: topEvent.time +
                         topEvent.duration });
                        {
                            const durationElapsed = now - topEvent.time;
                            const durationRatio = durationElapsed / topEvent.duration;
                            const start = this.lastWalkingStart;
                            const destination = queue.queueBegin(now);
                            const x = start.x + (destination.x - start.x) * durationRatio + wabble +
                             this.positionInGroup * Person.GROUP_SPACING;
                            const y = start.y + (destination.y - start.y) * durationRatio + wabble;
                            ctx.drawImage(this.picture, x, y, IMAGE_WIDTH, IMAGE_HEIGHT);
                        }
                        break;
                    case "IN_CRTP":
                        {
                            const seqNo = [topEvent.people].indexOf(this.id);
                            const serviceLocation = queue.serviceLocation;
                            this.lastWalkingStart = serviceLocation;
                            ctx.drawImage(this.picture, serviceLocation.x + seqNo * Person.GROUP_SPACING,
                             serviceLocation.y, IMAGE_WIDTH, IMAGE_HEIGHT);
                        }
                        break;
                    case "GO_TO_HOSPITAL":
                        queue.registerPeople([topEvent.person], { begin: topEvent.time, end: topEvent.time +
                         topEvent.duration });
                        {
                            const durationElapsed = now - topEvent.time;
                            const durationRatio = durationElapsed / topEvent.duration;
                            const start = this.lastWalkingStart;
                            const destination = queue.queueBegin(now);
                            const x = start.x + (destination.x - start.x) * durationRatio +
                             this.positionInGroup * Person.GROUP_SPACING + wabble;
                            const y = start.y + (destination.y - start.y) * durationRatio + wabble;
                            ctx.drawImage(this.picture, x, y, IMAGE_WIDTH, IMAGE_HEIGHT);
                        }
                        break;
                    case "HOSPITAL_LEAVE":
                        queue.removePeople([topEvent.person]);
                        {
                            if (now < topEvent.time + topEvent.duration) {
                                const serviceLocation = queue.serviceLocation;
                            }
                            else {
                                // TODO: Self destruct
                            }
                        }
                        break;
                    default:
                        console.warn("Unknown event: " + topEvent.event);
                }
            }
        }
        // -------------------------
        //  CANVAS LOGIC
        // -------------------------
        let stopTriggered = false;
        const begin = new Date().getTime();
        const Run = async (speed) => {
            const canvas = document.getElementById("animate");
            const ctx = canvas.getContext("2d");
            if (!ctx) {
                console.error("no context?");
                return;
            }

            const waitingRoomSpacing = 25;
            const treatmentRoomSpacing = 40;
            const events = SortAndInjectSequentialIDs(data.events);
            const corEvents = SortAndInjectSequentialIDs(no_corridor.time_events);
            const wrEvents = SortAndInjectSequentialIDs(no_waitingroom.time_events);            
            const mrEvents = SortAndInjectSequentialIDs(no_majors.time_events);
            const trEvents = SortAndInjectSequentialIDs(no_minors.time_events);
            const rrEvents = SortAndInjectSequentialIDs(no_resus.time_events);
            const srEvents = SortAndInjectSequentialIDs(no_sdec.time_events);
                   
            const waitingForED = Array.from(Array(data.waitingForED).keys()).map((i) => 
            new Queue("Patient waiting to be registered", 0, { x: 100, y: 300 + i * waitingRoomSpacing }, 0));
            const waitingRoomSeats = Array.from(Array(data.waitingRoomSeats).keys()).map((i) =>
             new Queue("WR", i + 1, { x: 300 + (Math.floor(i/7)) * 75, y: 75 + (i % 7) * waitingRoomSpacing },
              WAITING_ROOM_WIDTH));
            const treatmentRooms = Array.from(Array(data.treatmentRooms).keys()).map((i) =>
             new Queue("TR", i + 1, { x: 800 + (Math.floor(i/5)) * 50, y: 300 + (i % 5) * treatmentRoomSpacing },
              TREATMENT_WIDTH));
            const majorRooms = Array.from(Array(data.majorRooms).keys()).map((i) =>
             new Queue("MR", i + 1, { x: 300 + (Math.floor(i/5)) * 50, y: 300 + (i % 5) * treatmentRoomSpacing },
              TREATMENT_WIDTH));
            const resusRooms = Array.from(Array(data.resusRooms).keys()).map((i) =>
             new Queue("RR", i + 1, { x: 300 + (Math.floor(i/5)) * 50, y: 525 + (i % 5) * treatmentRoomSpacing },
              TREATMENT_WIDTH));
            const sdecRooms = Array.from(Array(data.sdecRooms).keys()).map((i) =>
             new Queue("SR", i + 1, { x: 700 + (Math.floor(i/5)) * 50, y: 525 + (i % 5) * treatmentRoomSpacing },
              TREATMENT_WIDTH));
            const xRayCT = Array.from(Array(data.xRayCt).keys()).map((i) =>
             new Queue("X-Ray/CT Rooms", 0, { x: 1100, y: 300 + i * treatmentRoomSpacing }, XRAYCT_WIDTH));
            const CRTP = Array.from(Array(data.CRTP).keys()).map((i) =>
             new Queue("Waiting for admission or discharge", 0, { x: 1350, y: 300 + i * treatmentRoomSpacing },
              XRAYCT_WIDTH));
            const hospital = Array.from(Array(data.hospital).keys()).map((i) =>
             new Queue("Exit ED and admit to hospital", 0, { x: 1500, y: 100 + i * treatmentRoomSpacing },
              XRAYCT_WIDTH));
            const exit = Array.from(Array(data.exit).keys()).map((i) =>
             new Queue("Exit ED without admission to hospital (discharge)", 0,
              { x: 1500, y: 500 + i * treatmentRoomSpacing }, 0));
            
            const personMap = {};
            var timehour = ""
            var timemin = ""
            var crtpSize = "0";
            var wrSize = "0";
            var mrSize = "0";
            var trSize = "0";
            var rrSize = "0";
            var srSize = "0";
            
            const Draw = () => {
                now += (0.01 * speed);
                let e = null;
                let cor = null;
                let wr = null;
                let mr = null;
                let tr = null;
                let rr = null;
                let sr = null;

                while (true) {
                    e = events.shift();
                    cor = corEvents.shift();
                    wr = wrEvents.shift();
                    mr = mrEvents.shift();
                    tr = trEvents.shift();
                    rr = rrEvents.shift();
                    sr = srEvents.shift();

                    if(!cor) { }
                    else if (cor.time > now) { corEvents.unshift(cor);}
                    else {
                        crtpSize = cor.size.toString();
                    }
                    if(!wr) { }
                    else if (wr.time > now) { wrEvents.unshift(wr);}
                    else {
                        wrSize = wr.size.toString();
                    }
                    if(!mr) { }
                    else if (mr.time > now) { mrEvents.unshift(mr);}
                    else {
                        mrSize = mr.size.toString();
                    }
                    if(!tr) { }
                    else if (tr.time > now) { trEvents.unshift(tr);}
                    else {
                        trSize = tr.size.toString();
                    }
                    if(!rr) { }
                    else if (rr.time > now) { rrEvents.unshift(rr);}
                    else {
                        rrSize = rr.size.toString();
                    }
                    if(!sr) { }
                    else if (sr.time > now) { srEvents.unshift(sr);}
                    else {
                        srSize = sr.size.toString();
                    }
                    if (!e) {
                        break;
                    }
                    else if (e.time > now) {
                        events.unshift(e);
                        break;
                    }

                    if (e.event === "ARRIVE_AT_ED") {
                        (e.peopleCreated || []).forEach((id) => (personMap[id] = new Person(id, e.acuity,
                         waitingForED, waitingRoomSeats, treatmentRooms, majorRooms, resusRooms, sdecRooms, xRayCT,
                          CRTP, hospital, exit)));
                    }
                    else if (e.people !== undefined) {
                        e.people.forEach((id) => personMap[id].registerEvent(e));
                    }
                    else if (e.person !== undefined) {
                        personMap[e.person].registerEvent(e);
                    }
                    else {
                        console.warn("Invalid event received", e);
                    }
                }
                ctx.globalCompositeOperation = "destination-over";
                ctx.clearRect(0, 0, 1800, 800);
                waitingForED.forEach((q) => q.draw(ctx, now));
                waitingRoomSeats.forEach((q) => q.draw(ctx, now));
                treatmentRooms.forEach((q) => q.draw(ctx, now));
                majorRooms.forEach((q) => q.draw(ctx, now));
                resusRooms.forEach((q) => q.draw(ctx, now));
                sdecRooms.forEach((q) => q.draw(ctx, now));
                xRayCT.forEach((q) => q.draw(ctx, now));
                CRTP.forEach((q) => q.draw(ctx, now));
                hospital.forEach((q) => q.draw(ctx, now));
                exit.forEach((q) => q.draw(ctx, now));
                Object.keys(personMap).forEach((id) => personMap[id].draw(ctx, now));

                if (Math.floor((now).toFixed(0) % 60 < 10)){ timemin = "0" + ((now).toFixed(0) % 60).toString() }
                else { timemin = ((now).toFixed(0) % 60).toString() }
                if (Math.floor((now).toFixed(0) / 60) % 24 < 10){ timehour = "0" +
                 (Math.floor((now).toFixed(0) / 60) % 24).toString() }
                else { timehour = (Math.floor((now).toFixed(0) / 60) % 24).toString() }
                ctx.font = '10px sans-serif';

                //Adding occupancy labels
                ctx.fillText("Occupancy: " + crtpSize, 1350, 340);
                ctx.fillText("Occupancy: " + " ( " + Math.round(100*wrSize/waitingRoomSeats.length) + " %) ", 300, 60); 
                ctx.fillText("Occupancy: " + " ( " +  Math.round(100*mrSize/majorRooms.length) + " %) ", 300, 290);   
                ctx.fillText("Occupancy: " + " ( " + Math.round(100*trSize/treatmentRooms.length) + " %) ", 800, 290);
                ctx.fillText("Occupancy: " + " ( " + Math.round(100*rrSize/resusRooms.length) + " %) ", 300, 510);  
                ctx.fillText("Occupancy: " + " ( " + Math.round(100*srSize/sdecRooms.length) + " %) ", 700, 510);

                ctx.font = '15px sans-serif';
                ctx.fillText("Waiting Room", 300, 50);

                //Adding labels to rooms
                ctx.fillText("Minors Room", 800, 280);
                ctx.fillText("Majors Room", 300, 280);
                ctx.fillText("Resus Room", 300, 500);
                ctx.fillText("Sdec Room", 700, 500);

                ctx.font = '20px sans-serif';
                ctx.fillText(`Duration`, 25, 175);            
                ctx.fillText(`Day ${Math.floor((now).toFixed(0) / (60 * 24)) + 1} Time = ${timehour}:${timemin}`,
                 25, 200);

                if (now < """ + str(time_end2) + """ && !stopTriggered) {
                    window.requestAnimationFrame(Draw);
                }
                else {
                    goButton.textContent = "Start";
                    stopTriggered = false;
                }
                ctx.font = '10px sans-serif';
            };
            window.requestAnimationFrame(Draw);
        };
        goButton.addEventListener("click", function () {
            if (this.textContent === "Start") {
                this.textContent = "Stop";
                const speed = parseInt(document.getElementById("speed").value, 10);
                Run(speed);
            }
            else {
                this.textContent = "Start";
                stopTriggered = true;
            }
        });
        pdfButton.addEventListener("click", function (e) {
            window.open("static/js/ED_Simulator.pdf");
        });
        aboutButton.addEventListener("click", function (e) {
            window.open("static/js/AboutEDSim.pdf");
        });
        submit.addEventListener("click", function (e) {
            loader.style.display = 'block';
        });
        """

    return var
