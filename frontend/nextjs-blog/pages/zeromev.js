import Head from "next/head";
import React, { useState, useEffect } from "react";
import axios from "axios";

export default function Home() {
  const backend = "http://127.0.0.1:5000/zeromev";
  const [zeromev, setZeromev] = useState({});
  useEffect(() => {
    axios
      .get(backend)
      .then((resp) => {
        setZeromev(resp.data);
      })
      .catch((err) => console.log(err));
  }, []);

  return (
    <div>
      <main>
        <div>
          {zeromev ? (
            <table id="searchers">
              <tbody>
                <tr>
                  <th>MEV Bot</th>
                  <th>Occurrences</th>
                </tr>
                {Object.entries(zeromev).map(([key, value], index) => {
                  return (
                    <tr key={index}>
                      <td>{key}</td>
                      <td>{value}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          ) : (
            <h1>Loading...</h1>
          )}
        </div>
      </main>
    </div>
  );
}
