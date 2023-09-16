import { indicoAxios, handleAxiosError } from "indico/utils/axios";

const SESSIONTABLE_SELECTOR =
  ".ngtimetable > .schedule > .timetable, .ngtimetable > .schedule > .timetable > .session," +
  ".ngtimetable > .schedule > .timetable > .break";
const TIMESLOT_SELECTOR = ".ngtimetable > .schedule > .timetable > .timeslot";
const ROOM_SELECTOR = ".ngtimetable > .rooms > .room";
const CONTRIBUTION_SELECTOR = ".timetable .contribution, .ngtimetable-unscheduled .contribution";

let dragnode = null;
let swapnode = null;
let columnwidth = 0;
let unitsPerHour = 0;
let granularity = 0;
let rowheight = 0;
let maxRooms = 0;

function dragStart(event) {
  event.dataTransfer.setData("text/plain", "hello");
  event.dataTransfer.effectAllowed = "move";
  event.dataTransfer.setDragImage(document.getElementById("dragcanvas"), 0, 0);

  columnwidth = Math.floor(document.querySelector(TIMESLOT_SELECTOR).offsetWidth / unitsPerHour);
  rowheight = document.querySelector(ROOM_SELECTOR).offsetHeight;
  maxRooms = document.querySelectorAll(".room").length - 1;

  dragnode = event.target;
  dragnode.classList.add("dragging");
  dragnode._originalParent = dragnode.parentNode;

  if (!dragnode.parentNode.classList.contains("ngtimetable-unscheduled")) {
    const dragsource = dragnode.parentNode.appendChild(document.getElementById("dragsource"));
    dragsource.style.gridColumn = dragnode.style.gridColumn;
    dragsource.style.gridRow = dragnode.style.gridRow;
    dragsource.classList.add("dragging");
  }

  const container = dragnode.closest(".session, .timetable");
  if (container) {
    dragnode._originalPosition = getDragCell(container, dragnode, event.clientX, event.clientY);
  }
}

function dragEnd(event) {
  if (event.dataTransfer.dropEffect === "none") {
    dragnode.style.gridColumnStart = `timeunit ${dragnode.dataset.timeunitStart}`;
    dragnode.style.gridRowStart = `room ${dragnode.dataset.roomIndex}`;
    dragnode.style.color = dragnode.dataset.color;
    dragnode.style.backgroundColor = dragnode.dataset.backgroundColor;
    dragnode.querySelector(".starttime").textContent = dragnode.dataset.startTime;
    dragnode.querySelector(".endtime").textContent = dragnode.dataset.endTime;

    dragnode._originalParent.appendChild(dragnode);
  }

  if (swapnode) {
    swapnode.classList.remove("dragging");
    swapnode._originalParent = null;
    swapnode._originalPosition = null;
    swapnode = null;
  }

  dragnode.classList.remove("dragging");
  dragnode._originalParent = null;
  dragnode._originalPosition = null;
  dragnode = null;

  const dragsource = document.getElementById("dragsource");
  dragsource.classList.remove("dragging");
}

function getDragCell(target, node, clientX, clientY) {
  const currentRect = target.getBoundingClientRect();
  const x = clientX - currentRect.left;
  const y = clientY - currentRect.top;

  const span = parseInt(node.dataset.timeunitSpan, 10);
  const maxUnits = parseInt(target.closest(".timetable").dataset.times, 10) - span;

  const column = Math.min(maxUnits, Math.floor(x / columnwidth));
  const row = Math.min(maxRooms, Math.floor(y / rowheight));

  return [column + 1, row + 1];
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

  const [column, row] = getDragCell(droptarget, dragnode, event.clientX, event.clientY);

  if (dragnode._originalPosition) {
    const hoverNode = document
      .elementFromPoint(event.clientX, event.clientY)
      .closest(".contribution");
    const [swapCol, swapRow] = swapnode?._originalPosition ?? [];
    const isWithin =
      swapnode &&
      column >= swapCol &&
      column <= swapCol + parseInt(swapnode.dataset.timeunitSpan, 10) &&
      swapRow === row;

    if (event.shiftKey && swapnode && !isWithin) {
      clearSwapNode();
    }

    if (event.shiftKey && !swapnode) {
      swapnode = hoverNode;
      if (swapnode) {
        swapnode._originalPosition = [
          parseInt(swapnode.dataset.timeunitStart, 10),
          parseInt(swapnode.dataset.roomIndex, 10),
        ];
        swapnode._originalParent = swapnode.parentNode;
        swapnode.classList.add("dragging");

        updateContributionForCell(swapnode, ...dragnode._originalPosition);
        dragnode._originalParent.appendChild(swapnode);
      }
    } else if (!event.shiftKey && swapnode) {
      clearSwapNode();
    }
  }

  droptarget.appendChild(dragnode);
  updateContributionForCell(dragnode, column, row);

  event.dataTransfer.dropEffect = "move";
}

function clearSwapNode() {
  updateContributionForCell(swapnode, ...swapnode._originalPosition);
  swapnode._originalParent.appendChild(swapnode);
  swapnode._originalParent = null;
  swapnode._originalPosition = null;
  swapnode.classList.remove("dragging");
  swapnode = null;
}

function updateContributionForCell(node, column, row) {
  const duration = parseInt(node.dataset.duration, 10);
  const { startTime, endTime } = getContributionTimes(column, duration);

  node.querySelector(".starttime").textContent = startTime.substring(0, 5);
  node.querySelector(".endtime").textContent = endTime.substring(0, 5);

  node.style.gridColumnStart = `timeunit ${column}`;
  node.style.gridRowStart = `room ${row}`;
}

function dragEnterUnscheduled(event) {
  event.preventDefault();
  event.stopPropagation();
  event.dataTransfer.dropEffect = "move";
  event.currentTarget.appendChild(dragnode);
  dragnode.style.color = dragnode.dataset.color;
  dragnode.style.backgroundColor = dragnode.dataset.backgroundColor;
  dragnode.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

function getContributionTimes(column, span = 0) {
  const timetable = dragnode.closest(".timetable");
  const session = dragnode.closest(".session");

  let daystartTimeunit = unitsPerHour * parseInt(timetable.firstElementChild.dataset.hour, 10);
  if (session) {
    daystartTimeunit += parseInt(session.dataset.timeunitStart, 10) - 1;
  }

  let startMinute = (daystartTimeunit + column - 1) * granularity;
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

  const [column, row] = getDragCell(event.currentTarget, dragnode, event.clientX, event.clientY);
  const timetable = dragnode.closest(".timetable");
  const datekey = timetable.dataset.date;

  dragnode.dataset.timeunitStart = column;
  dragnode.dataset.roomIndex = row;

  const data = {
    session: null,
    startDate: {
      date: `${datekey.substring(0, 4)}-${datekey.substring(4, 6)}-${datekey.substring(6, 8)}`,
      time: getContributionTimes(column).startTime,
      timezone: document.getElementById("tz-selector-link").textContent,
    },
    locationData: {
      inheriting: false,
    },
  };

  if (event.shiftKey && swapnode) {
    data.swapWith = parseInt(swapnode.dataset.id, 10);
  }

  const session = dragnode.closest(".session");
  if (session) {
    data.session = parseInt(session.dataset.id, 10);
    data.locationData.inheriting = true;
  } else {
    const roomNode = [...document.querySelectorAll(".rooms .room")][dragnode.dataset.roomIndex - 1];
    if (roomNode.dataset.roomId) {
      data.locationData.room_id = parseInt(roomNode.dataset.roomId, 10);
      data.locationData.venue_id = parseInt(roomNode.dataset.venueId, 10);
    } else {
      data.locationData.room_name = roomNode.textContent;
    }
  }

  if (dragnode.dataset.id) {
    const url = new URL(`./manage/move/${dragnode.dataset.id}`, window.location.href);
    indicoAxios.post(url.toString(), data).catch(handleAxiosError);
  } else {
    const url = new URL(
      `./manage/schedule/${dragnode.dataset.contributionId}`,
      window.location.href,
    );
    const lastdragnode = dragnode;
    indicoAxios.post(url.toString(), data).then((respdata) => {
      lastdragnode.dataset.id = respdata.data.id;
    }, handleAxiosError);
  }
}

function dragDropUnscheduled(event) {
  event.preventDefault();

  const thisdragnode = dragnode;

  if (thisdragnode.dataset.id) {
    const url = new URL(
      `../manage/timetable/entry/${dragnode.dataset.id}/delete`,
      window.location.href,
    );
    indicoAxios.post(url.toString()).then(() => delete thisdragnode.dataset.id, handleAxiosError);
  }
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

  const unscheduled = document.querySelector(".ngtimetable-unscheduled");
  unscheduled.addEventListener("dragover", dragEnterUnscheduled);
  unscheduled.addEventListener("drop", dragDropUnscheduled);

  unitsPerHour = parseInt(document.querySelector(".ngtimetable").dataset.unitsPerHour, 10);
  granularity = Math.floor(60 / unitsPerHour);
}

window.addEventListener("load", dragSetup, { once: true });
