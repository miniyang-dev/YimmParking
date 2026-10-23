import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { followRowLink } from "./rowLink";

function row(onFollow: () => void) {
  render(
    <table>
      <tbody>
        <tr onClick={followRowLink}>
          <td>a</td>
          <td>
            <a
              href="https://www.google.com/maps/dir/?api=1"
              onClick={(e) => {
                e.preventDefault(); // jsdom cannot navigate
                onFollow();
              }}
            >
              國光路
            </a>
          </td>
          <td>滿</td>
        </tr>
      </tbody>
    </table>,
  );
}

describe("followRowLink", () => {
  afterEach(cleanup);

  it("follows the row's link from anywhere in the row", () => {
    const follow = vi.fn();
    row(follow);
    fireEvent.click(screen.getByText("滿"));
    expect(follow).toHaveBeenCalledTimes(1);
  });

  it("does not follow it twice when the link itself is clicked", () => {
    const follow = vi.fn();
    row(follow);
    fireEvent.click(screen.getByText("國光路"));
    expect(follow).toHaveBeenCalledTimes(1);
  });
});
