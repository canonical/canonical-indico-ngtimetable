import { indicoAxios, handleAxiosError } from "indico/utils/axios";

const SESSIONTABLE_SELECTOR =
  ".ngtimetable > .schedule > .timetable, .ngtimetable > .schedule > .timetable > .session," +
  ".ngtimetable > .schedule > .timetable > .break";
const TIMESLOT_SELECTOR = ".ngtimetable > .schedule > .timetable > .timeslot";
const ROOM_SELECTOR = ".ngtimetable > .rooms > .room";
const CONTRIBUTION_SELECTOR = ".timetable .contribution";

let dragnode = null;
let columnwidth = 0;
let rowheight = 0;

function dragStart(event) {
  event.dataTransfer.setData("text/plain", "hello");
  event.dataTransfer.effectAllowed = "move";
  event.dataTransfer.setDragImage(document.getElementById("dragcanvas"), 0, 0);

  event.target.style.opacity = 0.4;

  dragnode = event.target;
}

function dragEnd(event) {
  dragnode.style.opacity = 1;

  if (event.dataTransfer.dropEffect === "none") {
    dragnode.style.gridColumnStart = `halfhour ${dragnode.dataset.halfhourStart}`;
    dragnode.style.gridRowStart = `room ${dragnode.dataset.room}`;
    dragnode.style.color = dragnode.dataset.color;
    dragnode.style.backgroundColor = dragnode.dataset.backgroundColor;
    dragnode.querySelector(".starttime").textContent = dragnode.dataset.startTime;
    dragnode.querySelector(".endtime").textContent = dragnode.dataset.endTime;
  }
  dragnode = null;
}

function getDragCell(target, clientX, clientY) {
  const currentRect = target.getBoundingClientRect();
  const x = clientX - currentRect.left;
  const y = clientY - currentRect.top;

  const column = Math.floor(x / columnwidth);
  const row = Math.floor(y / rowheight);

  return [column, row];
}

function dragOver(event) {
  event.preventDefault();
  event.stopPropagation();

  let droptarget = event.currentTarget;
  if (droptarget.classList.contains("break")) {
    event.dataTransfer.dropEffect = "none";
    return;
  } else if (droptarget.classList.contains("session")) {
    dragnode.style.color = droptarget.dataset.color;
    dragnode.style.backgroundColor = droptarget.dataset.backgroundColor;

    droptarget = droptarget.querySelector(".contributions");
  } else {
    dragnode.style.color = dragnode.dataset.color;
    dragnode.style.backgroundColor = dragnode.dataset.backgroundColor;
  }

  const [column, row] = getDragCell(droptarget, event.clientX, event.clientY);

  droptarget.appendChild(dragnode);
  dragnode.style.gridColumnStart = `halfhour ${column + 1}`;
  dragnode.style.gridRowStart = `room ${row + 1}`;

  const duration = parseInt(dragnode.dataset.duration, 10);
  const { startTime, endTime } = getContributionTimes(column, row, duration);

  dragnode.querySelector(".starttime").textContent = startTime.substring(0, 5);
  dragnode.querySelector(".endtime").textContent = endTime.substring(0, 5);

  event.dataTransfer.dropEffect = "move";
}

function getContributionTimes(column, row, span = 0) {
  const timetable = dragnode.closest(".timetable");
  const session = dragnode.closest(".session");

  let daystartHalfhour = 2 * parseInt(timetable.firstElementChild.dataset.hour, 10);
  if (session) {
    daystartHalfhour += parseInt(session.dataset.halfhourStart, 10) - 1;
  }

  let startMinute = (daystartHalfhour + column) * 30;
  let endMinute = startMinute + span;

  const startHour = Math.floor(startMinute / 60);
  const endHour = Math.floor(endMinute / 60);

  startMinute %= 60;
  endMinute %= 60;

  const startHourString = startHour.toString().padStart(2, "0");
  const startMinuteString = startMinute.toString().padStart(2, "0");
  const endHourString = endHour.toString().padStart(2, "0");
  const endMinuteString = endMinute.toString().padStart(2, "0");

  return {
    startTime: `${startHourString}:${startMinuteString}:00`,
    endTime: `${endHourString}:${endMinuteString}:00`,
  };
}

function dragDrop(event) {
  event.preventDefault();
  event.stopPropagation();

  const [column, row] = getDragCell(event.currentTarget, event.clientX, event.clientY);
  const timetable = dragnode.closest(".timetable");
  const datekey = timetable.dataset.date;

  dragnode.dataset.halfhourStart = column + 1;
  dragnode.dataset.room = row + 1;

  const data = {
    session: null,
    startDate: {
      date: `${datekey.substring(0, 4)}-${datekey.substring(4, 6)}-${datekey.substring(6, 8)}`,
      time: getContributionTimes(column, row).startTime,
      timezone: document.getElementById("tz-selector-link").textContent,
    },
    locationData: {
      inheriting: false,
    },
  };

  const session = dragnode.closest(".session");
  if (session) {
    data.session = parseInt(session.dataset.id, 10);
    data.locationData.inheriting = true;
  } else {
    const roomNode = [...document.querySelectorAll(".rooms .room")][dragnode.dataset.room - 1];
    if (roomNode.dataset.roomId) {
      data.locationData.room_id = parseInt(roomNode.dataset.roomId, 10);
      data.locationData.venue_id = parseInt(roomNode.dataset.venueId, 10);
    } else {
      data.locationData.room_name = roomNode.textContent;
    }
  }

  const url = new URL(`./manage/move/${dragnode.dataset.id}`, window.location.href);
  indicoAxios.post(url.toString(), data).catch(handleAxiosError);
}
function dragSetup() {
  if (document.querySelector(".ngtimetable").dataset.management !== "true") {
    return;
  }
  for (const elem of document.querySelectorAll(CONTRIBUTION_SELECTOR)) {
    elem.addEventListener("dragstart", dragStart);
    elem.addEventListener("dragend", dragEnd);
  }

  for (const node of document.querySelectorAll(SESSIONTABLE_SELECTOR)) {
    node.addEventListener("dragover", dragOver);
    node.addEventListener("drop", dragDrop);
  }

  columnwidth = Math.floor(document.querySelector(TIMESLOT_SELECTOR).offsetWidth / 2);
  rowheight = document.querySelector(ROOM_SELECTOR).offsetHeight;
}

window.addEventListener("load", dragSetup, { once: true });
